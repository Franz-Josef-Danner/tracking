# Helper/clean_error_tracks.py
# Sichtbares UI-Feedback (Statusleiste + Progress) + finaler clean_short_tracks-Pass

import bpy
from .multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from .segments import track_has_internal_gaps
from .mute_ops import mute_after_last_marker, mute_unassigned_markers
from .split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup

__all__ = ("run_clean_error_tracks",)


def _track_ptr(t):
    try:
        return int(t.as_pointer())
    except Exception:
        return id(t)


def _clip_override(context):
    """Sicher in den CLIP_EDITOR kontexten."""
    win = context.window
    if not win:
        return None
    scr = getattr(win, "screen", None)
    if not scr:
        return None
    for area in scr.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None


def _deps_sync(context):
    deps = context.evaluated_depsgraph_get()
    deps.update()
    bpy.context.view_layer.update()
    context.scene.frame_set(context.scene.frame_current)


def _status(wm, text: str | None):
    """Kurztext in der Statusleiste setzen/entfernen."""
    try:
        wm.status_text_set(text)
    except Exception:
        pass


def _pulse_ui():
    """Sanftes UI-Refresh, damit Progress/Status sichtbar ist."""
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        # Fallback: nichts, Progress wird beim nächsten Draw sichtbar
        pass


def run_clean_error_tracks(context, *, show_popups: bool = False):
    """
    Führt Clean Error Tracks mit sichtbaren UI-Schritten aus:
      1) Prepare/Sync
      2) Multiscale-Grid-Clean
      3) Gap-Split + Recursive-Cleanup (+ leere Duplikate entfernen)
      4) Safety-Pässe (mute)
      5) Final Short Clean
    Rückgabe: {'FINISHED'} oder {'CANCELLED'}.
    """
    scene = context.scene
    wm = context.window_manager
    ovr = _clip_override(context)
    if not ovr:
        if show_popups:
            wm.popup_menu(lambda self, ctx: self.layout.label(text="Kein CLIP_EDITOR-Kontext gefunden."),
                          title="Clean Error Tracks", icon='CANCEL')
        print("[CleanError] ERROR: Kein gültiger CLIP_EDITOR-Kontext gefunden.")
        return {'CANCELLED'}

    # Fortschritt vorbereiten (5 Hauptschritte)
    steps_total = 5
    try:
        wm.progress_begin(0, steps_total)
    except Exception:
        pass

    def step_update(i, label):
        _status(wm, f"Clean Error Tracks – {label} ({i}/{steps_total})")
        try:
            wm.progress_update(i)
        except Exception:
            pass
        _pulse_ui()

    # ---------- 1) PREPARE ----------
    step_update(1, "Prepare")
    with context.temp_override(**ovr):
        _deps_sync(context)
        clip = ovr["space_data"].clip
        if not clip:
            if show_popups:
                wm.popup_menu(lambda self, ctx: self.layout.label(text="Kein aktiver Clip."),
                              title="Clean Error Tracks", icon='CANCEL')
            print("[CleanError] ERROR: Kein aktiver Clip.")
            _status(wm, None)
            try:
                wm.progress_end()
            except Exception:
                pass
            return {'status': 'CANCELLED'}

    # ---------- 2) MULTISCALE CLEAN ----------
    step_update(2, "Multiscale Clean")
    with context.temp_override(**ovr):
        w, h = clip.size
        fr = (scene.frame_start, scene.frame_end)
        deleted = multiscale_temporal_grid_clean(
            context, ovr["area"], ovr["region"], ovr["space_data"],
            list(clip.tracking.tracks), fr, w, h,
            grid=(6, 6), start_delta=None, min_delta=3,
            outlier_q=1, hysteresis_hits=2, min_cell_items=4
        )
        print(f"[MultiScale] total deleted: {deleted}")
        _deps_sync(context)

    # ---------- 3) GAP SPLIT + RECURSIVE ----------
    # Globale Zähler (vor allen Operationen)
    with context.temp_override(**ovr):
        tracks_global_before = len(clip.tracking.tracks)
        markers_global_before = sum(len(t.markers) for t in clip.tracking.tracks)

    step_update(3, "Gap Split & Recursive Cleanup")
    with context.temp_override(**ovr):
        tracks = clip.tracking.tracks
        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]

        tracks_before = len(tracks)
        markers_before = sum(len(t.markers) for t in tracks)
        deleted_any = deleted > 0
        recursive_changed = False

        if not original_tracks:
            msg = "Keine Tracks mit internen Lücken – Split übersprungen."
            print(f"[CleanError] {msg}")
            if show_popups:
                wm.popup_menu(lambda self, ctx, m=msg: self.layout.label(text=m),
                              title="Clean Error Tracks", icon='INFO')
        else:
            existing_names = {t.name for t in tracks}
            for t in tracks:
                t.select = False
            for t in original_tracks:
                t.select = True

            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            _deps_sync(context)

            all_names_after = {t.name for t in tracks}
            new_names = all_names_after - existing_names
            new_tracks = [t for t in tracks if t.name in new_names]

            clear_path_on_split_tracks_segmented(
                context, ovr["area"], ovr["region"], ovr["space_data"],
                original_tracks, new_tracks
            )

            changed_in_recursive = recursive_split_cleanup(
                context, ovr["area"], ovr["region"], ovr["space_data"],
                tracks
            )
            if (isinstance(changed_in_recursive, bool) and changed_in_recursive) or \
               (isinstance(changed_in_recursive, int) and changed_in_recursive > 0):
                recursive_changed = True

            # Leere Duplikate entsorgen (damit sie nicht als Änderung zählen)
            empty_dupes = [t for t in new_tracks if len(t.markers) == 0]
            if empty_dupes:
                for t in tracks:
                    t.select = False
                for t in empty_dupes:
                    t.select = True
                bpy.ops.clip.delete_track()
                _deps_sync(context)

        tracks_after = len(tracks)
        markers_after = sum(len(t.markers) for t in tracks)
        made_changes = bool(
            deleted_any or
            (tracks_after != tracks_before) or
            (markers_after != markers_before) or
            recursive_changed
        )
        print(f"[CleanError] Changes? {made_changes} | "
              f"tracks: {tracks_before}->{tracks_after} | "
              f"markers: {markers_before}->{markers_after} | "
              f"recursive_changed={recursive_changed}")

    # ---------- 4) SAFETY ----------
    step_update(4, "Safety Passes")
    with context.temp_override(**ovr):
        tracks = clip.tracking.tracks
        for t in tracks:
            mute_after_last_marker(t, scene.frame_end)
        mute_unassigned_markers(tracks)
        _deps_sync(context)

    # ---------- 5) FINAL SHORT CLEAN ----------
    step_update(5, "Final Short Clean")
    with context.temp_override(**ovr):
        from .clean_short_tracks import clean_short_tracks as _short
        scn = context.scene

        # Gate einmalig deaktivieren, damit dieser Pass sicher läuft
        prev_skip = bool(scn.get("__skip_clean_short_once", False))
        try:
            scn["__skip_clean_short_once"] = False
            frames = int(getattr(scn, "frames_track", 25) or 25)
            _short(
                context,
                min_len=frames,
                action="DELETE_TRACK",
                respect_fresh=True,   # frische Namen weiterhin schonen
                verbose=True,
            )
        finally:
            scn["__skip_clean_short_once"] = prev_skip

        _deps_sync(context)

    # ---------- Abschluss ----------
    if show_popups:
        wm.popup_menu(lambda self, ctx: self.layout.label(text="Abgeschlossen."),
                      title="Clean Error Tracks", icon='CHECKMARK')

    _status(wm, None)
    try:
        wm.progress_end()
    except Exception:
        pass

    # Globale Zähler (nach allen Operationen)
    with context.temp_override(**ovr):
        tracks_global_after = len(clip.tracking.tracks)
        markers_global_after = sum(len(t.markers) for t in clip.tracking.tracks)

    deleted_tracks_global = max(0, tracks_global_before - tracks_global_after)
    deleted_markers_global = max(0, markers_global_before - markers_global_after)
    deleted_any_global = (deleted_tracks_global > 0) or (deleted_markers_global > 0)

    result = {
        'status': 'FINISHED',
        'deleted_any': bool(deleted_any_global),
        'deleted_tracks': int(deleted_tracks_global),
        'deleted_markers': int(deleted_markers_global),
        'multiscale_deleted': int(deleted),
        'changes_step3': bool(made_changes),
        'tracks_before': int(tracks_global_before),
        'tracks_after': int(tracks_global_after),
        'markers_before': int(markers_global_before),
        'markers_after': int(markers_global_after),
    }
    print(f"[CleanError] SUMMARY: {result}")
    return result

