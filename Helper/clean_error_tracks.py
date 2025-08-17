# file: Helper/clean_error_tracks.py  (deine neue Version)
import bpy
from .multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from .segments import track_has_internal_gaps
from .mute_ops import mute_after_last_marker, mute_unassigned_markers
from .split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup
from .clean_short_tracks import clean_short_tracks  # <-- NEU

__all__ = ("run_clean_error_tracks",)

def _clip_override(context):
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

def _notify(cb, step, msg="", progress=None):
    """Kleiner Safe-Notify: cb(step:str, msg:str, progress:float|None)"""
    if cb:
        try:
            cb(step, msg, progress)
        except Exception:
            pass

def run_clean_error_tracks(context, notify=None, do_ui_report=True):
    """
    Führt den Clean-Workflow aus und meldet Zwischenschritte via `notify`.
    Rückgabe: {'FINISHED'} oder {'CANCELLED'}.

    notify: callable(step:str, msg:str, progress:float|None)
    do_ui_report: wenn True, werden am Ende kurze Reports ins UI geschrieben.
    """
    scene = context.scene
    ovr = _clip_override(context)
    if not ovr:
        _notify(notify, "error", "Kein CLIP_EDITOR-Kontext.", 0.0)
        return {'CANCELLED'}

    with context.temp_override(**ovr):
        deps = context.evaluated_depsgraph_get()
        deps.update()
        bpy.context.view_layer.update()
        scene.frame_set(scene.frame_current)

        clip = ovr["space_data"].clip
        tracks = clip.tracking.tracks
        w, h = clip.size
        fr = (scene.frame_start, scene.frame_end)

        # --- 1) Multiscale-Grid-Clean -------------------------------------------------
        _notify(notify, "grid_clean:start", "Multiscale Grid Clean läuft …", 0.10)
        deleted = multiscale_temporal_grid_clean(
            context, ovr["area"], ovr["region"], ovr["space_data"],
            list(tracks), fr, w, h,
            grid=(6, 6), start_delta=None, min_delta=3,
            outlier_q=0.90, hysteresis_hits=2, min_cell_items=4
        )
        _notify(notify, "grid_clean:end", f"Gelöscht: {deleted}", 0.30)

        deps.update(); bpy.context.view_layer.update(); scene.frame_set(scene.frame_current)

        # --- 2) Gap-Erkennung & Split --------------------------------------------------
        _notify(notify, "split:start", "Lücken analysieren & Duplikate erstellen …", 0.35)
        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        new_tracks = []
        recursive_changed = False

        if not original_tracks:
            _notify(notify, "split:skip", "Keine Tracks mit internen Lücken – Split übersprungen.", 0.45)
        else:
            existing_names = {t.name for t in tracks}
            for t in tracks: t.select = False
            for t in original_tracks: t.select = True

            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()

            deps.update(); bpy.context.view_layer.update(); scene.frame_set(scene.frame_current)

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
            recursive_changed = bool(
                (isinstance(changed_in_recursive, bool) and changed_in_recursive) or
                (isinstance(changed_in_recursive, int) and changed_in_recursive > 0)
            )

            # Leere Duplikate entfernen (kosmetisch & korrektes Delta)
            empty_dupes = [t for t in new_tracks if len(t.markers) == 0]
            if empty_dupes:
                for t in tracks: t.select = False
                for t in empty_dupes: t.select = True
                bpy.ops.clip.delete_track()
                deps.update(); bpy.context.view_layer.update(); scene.frame_set(scene.frame_current)

            _notify(notify, "split:end", f"Neue Tracks: {len(new_tracks)}; recursive_changed={recursive_changed}", 0.55)

        # --- 3) Safety-Pässe -----------------------------------------------------------
        _notify(notify, "safety:start", "Safety-Pässe (Mute/After-Last) …", 0.65)
        mute_unassigned_markers(tracks)
        for t in tracks:
            mute_after_last_marker(t, scene.frame_end)
        _notify(notify, "safety:end", "Safety abgeschlossen.", 0.75)

        # --- 4) Finaler Short-Track-Cleanup (NEU) -------------------------------------
        try:
            frames_limit = int(scene.get("frames_track", 0)) or getattr(scene, "frames_track", 0) or 0
        except Exception:
            frames_limit = 0
        if frames_limit > 0:
            _notify(notify, "short_clean:start", f"Final Short-Clean (< {frames_limit} Frames) …", 0.82)
            try:
                clean_short_tracks(context, action='DELETE_TRACK', frames=frames_limit)
                _notify(notify, "short_clean:end", "Short-Clean fertig.", 0.88)
            except Exception as e:
                _notify(notify, "short_clean:warn", f"Short-Clean fehlgeschlagen: {e}", 0.88)
        else:
            _notify(notify, "short_clean:skip", "Kein frames_track gesetzt – übersprungen.", 0.82)

        # --- 5) Finaler Graph-Sync -----------------------------------------------------
        deps.update()
        bpy.context.view_layer.update()
        scene.frame_set(scene.frame_current)
        _notify(notify, "done", "Clean Error Tracks abgeschlossen.", 1.0)

    if do_ui_report:
        # kurzer UI‑Report
        bpy.context.window_manager.popup_menu(
            lambda self, ctx: self.layout.label(text="Clean Error Tracks abgeschlossen."),
            title="Clean Error Tracks", icon='INFO'
        )

    return {'FINISHED'}
