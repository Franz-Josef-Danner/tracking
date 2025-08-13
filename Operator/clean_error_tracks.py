# Operator/clean_error_tracks.py
import bpy
from ..Helper.multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from ..Helper.segments import track_has_internal_gaps
from ..Helper.mute_ops import mute_after_last_marker, mute_unassigned_markers
from ..Helper.split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup

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


class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(getattr(context, "space_data", None)) and bool(getattr(context.space_data, "clip", None))

    def execute(self, context):
        scene = context.scene

        # --- 1) CLIP_EDITOR-Kontext holen
        ovr = _clip_override(context)
        if not ovr:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        # --- 2) Graph sync vor Start
        with context.temp_override(**ovr):
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            scene.frame_set(scene.frame_current)

            # --- 3) Multiscale-Grid-Clean
            clip = ovr["space_data"].clip
            w, h = clip.size
            fr = (scene.frame_start, scene.frame_end)

            deleted = multiscale_temporal_grid_clean(
                context, ovr["area"], ovr["region"], ovr["space_data"],
                list(clip.tracking.tracks), fr, w, h,
                grid=(6, 6), start_delta=None, min_delta=3,
                outlier_q=0.90, hysteresis_hits=2, min_cell_items=4
            )
            print(f"[MultiScale] total deleted: {deleted}")

            # --- 4) Gap-Erkennung & Aufteilung
            tracks = clip.tracking.tracks
            original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
            
            # Baselines vor mutierenden Schritten
            tracks_before = len(tracks)
            markers_before = sum(len(t.markers) for t in tracks)
            
            deleted_any = deleted > 0
            new_tracks = []
            recursive_changed = False
            
            if not original_tracks:
                print("[CleanError] Keine Tracks mit internen Lücken – überspringe Split.")
            else:
                # Duplizieren nur der gap-tracks
                existing_names = {t.name for t in tracks}
                for t in tracks:
                    t.select = False
                for t in original_tracks:
                    t.select = True
            
                bpy.ops.clip.copy_tracks()
                bpy.ops.clip.paste_tracks()
            
                deps = context.evaluated_depsgraph_get(); deps.update()
                bpy.context.view_layer.update(); scene.frame_set(scene.frame_current)
            
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
            
                # **NEU**: leere Duplikate entfernen, damit sie nicht als Änderung zählen
                empty_dupes = [t for t in new_tracks if len(t.markers) == 0]
                if empty_dupes:
                    for t in tracks:
                        t.select = False
                    for t in empty_dupes:
                        t.select = True
                    bpy.ops.clip.delete_track()
                    deps = context.evaluated_depsgraph_get(); deps.update()
                    bpy.context.view_layer.update(); scene.frame_set(scene.frame_current)
            
            # Struktur-Deltas nach allen Schritten ermitteln
            tracks_after = len(tracks)
            markers_after = sum(len(t.markers) for t in tracks)
            
            made_changes = bool(
                deleted_any or
                (tracks_after != tracks_before) or
                (markers_after != markers_before) or
                recursive_changed
            )


            # --- 5) Safety Passes
            mute_unassigned_markers(tracks)
            for t in tracks:
                mute_after_last_marker(t, scene.frame_end)

            # --- 6) Graph sync nach Cleanup
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            scene.frame_set(scene.frame_current)

            # --- 7) Routing (strict gating)
            try:
                if made_changes:
                    print("[Router] Änderungen erkannt → marker_adapt_boost + find_low_marker_frame")
                    try:
                        bpy.ops.clip.marker_adapt_boost('EXEC_DEFAULT')
                        print("[Router] marker_adapt_boost ok.")
                    except Exception as ex:
                        self.report({'WARNING'}, f"marker_adapt_boost fehlgeschlagen: {ex}")

                    try:
                        bpy.ops.clip.find_low_marker_frame('INVOKE_DEFAULT')
                        print("[Router] find_low_marker_frame gestartet.")
                    except Exception as ex:
                        self.report({'WARNING'}, f"find_low_marker_frame fehlgeschlagen: {ex}")
                else:
                    print("[Router] Keine Änderungen mehr → solve_watch_clean")
                    bpy.ops.clip.solve_watch_clean('INVOKE_DEFAULT')
            except Exception as ex:
                self.report({'WARNING'}, f"Routing fehlgeschlagen: {ex}")

        return {'FINISHED'}
