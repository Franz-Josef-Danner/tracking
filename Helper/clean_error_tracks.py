import bpy
from .multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from .segments import track_has_internal_gaps
from .mute_ops import mute_after_last_marker, mute_unassigned_markers
from .split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup

__all__ = ("run_clean_error_tracks",)


# ---------------------------------------------------------------------------
# Fallback-Helper (werden nur genutzt, wenn sie nicht bereits importiert sind)
# ---------------------------------------------------------------------------
try:
    _clip_override
except NameError:
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
                        return {
                            'area': area,
                            'region': region,
                            'space_data': area.spaces.active
                        }
        return None

try:
    _deps_sync
except NameError:
    def _deps_sync(context):
        deps = context.evaluated_depsgraph_get()
        deps.update()
        bpy.context.view_layer.update()
        context.scene.frame_set(context.scene.frame_current)

try:
    _status
except NameError:
    def _status(wm, text: str | None):
        try:
            wm.status_text_set(text)
        except Exception:
            pass

try:
    _pulse_ui
except NameError:
    def _pulse_ui():
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass


# ---------------------------------
# Utility
# ---------------------------------
def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a (soft) and b (original) by t∈[0,1]."""
    return (1.0 - t) * a + t * b


def run_clean_error_tracks(context, *, show_popups: bool = False, soften: float = 0.5):
    """
    Clean Error Tracks mit sichtbaren UI-Schritten.
    soften (0..1) reduziert Aggressivität:
      0.0 = maximal weich (löscht am wenigsten)
      0.5 = moderat (etwas aggressiver als vorherige 0.5-Version)
      1.0 = ursprüngliches Verhalten
    """
    soften = max(0.0, min(soften, 1.0))  # clamp
    scene = context.scene
    wm = context.window_manager
    ovr = _clip_override(context)
    if not ovr:
        if show_popups:
            wm.popup_menu(
                lambda self, ctx: self.layout.label(text="Kein CLIP_EDITOR-Kontext gefunden."),
                title="Clean Error Tracks", icon='CANCEL'
            )
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
                wm.popup_menu(
                    lambda self, ctx: self.layout.label(text="Kein aktiver Clip."),
                    title="Clean Error Tracks", icon='CANCEL'
                )
            _status(wm, None)
            try:
                wm.progress_end()
            except Exception:
                pass
            return {'CANCELLED'}

    # ---------- 2) MULTISCALE CLEAN (leicht stärker als vorheriges soften=0.5) ----------
    step_update(2, "Multiscale Clean")
    with context.temp_override(**ovr):
        w, h = clip.size
        fr = (scene.frame_start, scene.frame_end)

        # Zielwerte:
        #   Original (hart):          outlier_q=2, hysteresis=2, min_items=4, min_delta=3
        #   Sehr weich (soft=0.0):    outlier_q=4, hysteresis=3, min_items=6, min_delta=4
        # Wir lerpen zwischen "weich" (a) und "original" (b) mit soften∈[0..1].
        outlier_q_f   = _lerp(4.0, 2.0, soften)
        hysteresis_f  = _lerp(3.0, 2.0, soften)
        min_items_f   = _lerp(6.0, 4.0, soften)
        min_delta_f   = _lerp(4.0, 3.0, soften)

        # Rundung/Ganzzahlen
        outlier_q = int(round(outlier_q_f))
        hysteresis_hits = int(round(hysteresis_f))
        min_cell_items = int(round(min_items_f))
        min_delta = int(round(min_delta_f))

        # *Verstärkung ggü. deiner letzten soften=0.5-Version*:
        # Durch das lineare Mapping liegen die Parameter etwas näher an "Original".
        # Beispiel soften=0.5 -> outlier_q≈3, hysteresis≈2, min_items≈5, min_delta≈4.

        deleted = multiscale_temporal_grid_clean(
            context, ovr["area"], ovr["region"], ovr["space_data"],
            list(clip.tracking.tracks), fr, w, h,
            grid=(6, 6), start_delta=None, min_delta=min_delta,
            outlier_q=outlier_q, hysteresis_hits=hysteresis_hits, min_cell_items=min_cell_items
        )
        _deps_sync(context)

    # ---------- 3) GAP SPLIT + RECURSIVE ----------
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

            # Leere Duplikate entsorgen
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

    # ---------- 4) SAFETY ----------
    step_update(4, "Safety Passes")
    with context.temp_override(**ovr):
        tracks = clip.tracking.tracks
        for t in tracks:
            mute_after_last_marker(t, scene.frame_end)
        mute_unassigned_markers(tracks)
        _deps_sync(context)

    # ---------- 5) FINAL SHORT CLEAN (etwas stärker) ----------
    step_update(5, "Final Short Clean")
    with context.temp_override(**ovr):
        from .clean_short_tracks import clean_short_tracks as _short
        scn = context.scene

        prev_skip = bool(scn.get("__skip_clean_short_once", False))
        try:
            scn["__skip_clean_short_once"] = False

            base_frames = int(getattr(scn, "frames_track", 25) or 25)

            # Etwas stärker als vorher: bei soften=0.5 nun ~60% von base statt ~50%.
            # Bei soften<0.5 verhindern wir zu weiche Werte über Untergrenze 0.35*base.
            scale = max(0.35, soften * 1.2)  # 0.5 -> 0.6 ; 0.8 -> 0.96 (nahe original)
            frames_eff = max(6, int(round(base_frames * min(scale, 1.0))))


            _short(
                context,
                min_len=frames_eff,
                action="DELETE_TRACK",
                respect_fresh=True,
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
        'soften': float(soften),
    }
    return result
