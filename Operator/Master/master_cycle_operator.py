# master_cycle_operator.py
import bpy
import uuid
import ast
from bpy.types import Operator, Context

# ---- Helper Imports ---------------------------------------------------------
from ...Helper.low_marker_frame_solve import find_first_weak_frame_solve
from ...Helper.filter_tracks import filter_problematic_tracks
from ...Helper.update_default_sizes import update_default_sizes
from ...Helper.find_clip_editor_area import find_clip_editor_area
from ...Helper.delete import delete_tracks_by_names
from ...Helper.threshold_stats import log_threshold_extrema

# ===================================================================
# Zentrale Hilfsfunktion: UUID-basierte Track-Speicherung in Scene
# ===================================================================
def store_tracks_in_scene(scene, context, key="good_tracks"):
    log_key = str(key).upper()

    print(f"[{log_key}][STORE] -------------------------------------------")
    print(f"[{log_key}][STORE] Start storing tracks in scene for key='{key}'")

    clip = None
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        clip = space.clip
    if not clip:
        clip = getattr(context.scene.tracking, "active", None)
    if not clip:
        print(f"[{log_key}][STORE][WARN] No active clip found – aborting store_tracks_in_scene()")
        return

    tracking = clip.tracking
    all_tracks = list(tracking.tracks)
    print(f"[{log_key}][STORE] Found {len(all_tracks)} tracks in clip '{getattr(clip, 'name', '<unnamed>')}'")

    # ------------------------------------------------------------
    # Lösche nur die eigenen GOOD_TRACKS Keys, wenn wir GOOD erzeugen
    # ------------------------------------------------------------
    if key == "good_tracks":
        # Vorher-Status loggen
        existing_keys = {}
        for k in ("good_tracks", "good_tracks_names", "good_tracks_uuid_map"):
            if k in scene:
                existing_keys[k] = scene.get(k)

        if existing_keys:
            msg_parts = []
            for k, v in existing_keys.items():
                length_info = "n/a"
                try:
                    if isinstance(v, (list, tuple)):
                        length_info = len(v)
                    elif isinstance(v, str):
                        length_info = len(v)
                except Exception:
                    pass
                msg_parts.append(f"{k} (len={length_info})")
            print(f"[GOOD_TRACKS][DELETE] Existing GOOD_* keys before delete: {', '.join(msg_parts)}")
        else:
            print("[GOOD_TRACKS][DELETE] No existing GOOD_* keys found before delete.")

        for k in ("good_tracks", "good_tracks_names", "good_tracks_uuid_map"):
            if k in scene:
                print(f"[GOOD_TRACKS][DELETE] Deleting scene['{k}']")
                del scene[k]

        print("[GOOD_TRACKS][DELETE] GOOD_* keys cleanup completed.")

    uuid_list, name_list, uuid_map = [], [], {}
    for t in all_tracks:
        uid = str(uuid.uuid4())
        uuid_list.append(uid)
        name_list.append(t.name)
        uuid_map[uid] = t.name

    scene[key] = uuid_list
    scene[f"{key}_names"] = name_list
    scene[f"{key}_uuid_map"] = str(uuid_map)

    print(f"[{log_key}][STORE] Stored {len(uuid_list)} tracks in scene as '{key}'")
    if name_list:
        preview = ", ".join(name_list[:10])
        print(f"[{log_key}][STORE] First up to 10 track names: {preview}")
    else:
        print(f"[{log_key}][STORE] No track names stored (empty list).")

    print(f"[{log_key}][STORE] Done.")
    print(f"[{log_key}][STORE] -------------------------------------------")


# ===================================================================
# Haupt-Operator
# ===================================================================
class KAISERLICHTRACKER_OT_master_cycle_operator(Operator):
    """Master Operator – Sets the playhead to the frame with the fewest active markers"""
    bl_idname = "kaiserlich_tracker.master_cycle_operator"
    bl_label = "Master Operator"
    bl_description = "Sets the playhead to the first frame with the lowest number of active markers"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------------
    # Interne Clip-Refresh-Helfer
    # ------------------------------------------------------------------
    def _force_clip_refresh(self, context: Context, clip) -> None:
        try:
            window, area, region, space = find_clip_editor_area(
                getattr(getattr(context, "space_data", None), "clip", None) or clip
            )
        except Exception:
            return

        try:
            if space:
                space.clip = clip
            context.view_layer.update()
        except Exception:
            pass

        try:
            if all((window, area, region, space)):
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
                    bpy.ops.clip.select_all(action='DESELECT')
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Rebuild Good Tracks
    # ------------------------------------------------------------------
    def _rebuild_good_tracks(self, context: Context, reason: str = ""):
        scene = context.scene
        clip = (
            getattr(getattr(context, "space_data", None), "clip", None)
            or getattr(context, "edit_movieclip", None)
            or getattr(getattr(scene, "tracking", None), "active", None)
        )
        if not clip or not hasattr(clip, "tracking"):
            print(f"[GOOD_TRACKS][REBUILD][WARN] No valid clip/tracking found – rebuild aborted (reason='{reason}')")
            return

        print(f"[GOOD_TRACKS][REBUILD] Rebuild requested (reason='{reason}')")
        print(f"[GOOD_TRACKS][REBUILD] Clip: '{getattr(clip, 'name', '<unnamed>')}'")

        self._force_clip_refresh(context, clip)
        store_tracks_in_scene(scene, context, key="good_tracks")

        print("[GOOD_TRACKS][REBUILD] Rebuild completed.")

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------
    def execute(self, context: Context):
        scene = context.scene

        # ===============================================================
        # Scene-Bereinigung (alte Daten entfernen)
        # ===============================================================
        try:
            # good_tracks* wurden hier entfernt – jetzt bleiben sie erhalten
            keys_to_delete = [
                "calibrate_tracks", "calibrate_tracks_names", "calibrate_tracks_uuid_map",
                "frame_value_cache", "kaiserlich_best_thresholds"
            ]
            for _k in keys_to_delete:
                if _k in scene:
                    if _k.startswith("best_tracks"):
                        print(f"[BEST_TRACKS][DELETE] Removing scene['{_k}'] in execute()-cleanup")
                    else:
                        print(f"[SCENE][CLEANUP] Removing scene['{_k}'] in execute()-cleanup")
                    del scene[_k]
        except Exception as e:
            print(f"[SCENE][CLEANUP][ERROR] Exception during initial cleanup: {e}")
            pass

        frame = find_first_weak_frame_solve(context)

        # ===================================================================
        # Weiterer Ablauf (wie zuvor)
        # ===================================================================
        if frame is None:
            try:
                window, area, region, space = find_clip_editor_area(
                    getattr(getattr(context, "space_data", None), "clip", None)
                )

                if not all((window, area, region, space)):
                    raise RuntimeError("No CLIP_EDITOR area found – cannot continue cleanup")

                clip_ref = getattr(getattr(context, "space_data", None), "clip", None)
                if getattr(space, "clip", None) is None and clip_ref:
                    space.clip = clip_ref

                clip_obj = getattr(space, "clip", None)
                if not clip_obj:
                    raise RuntimeError("No active clip in current context")

                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.clip.filter_tracks(track_threshold=30.0)
                    tracking = clip_obj.tracking
                    flagged_names = [t.name for t in tracking.tracks if t.select]
                    if flagged_names:
                        print(f"[TRACKS][FILTER] Deleting {len(flagged_names)} flagged tracks after clip.filter_tracks()")
                        delete_tracks_by_names(bpy.context, flagged_names)
                    else:
                        print("[TRACKS][FILTER] No tracks flagged for deletion after clip.filter_tracks()")

                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    print("[TRACKS][FILTER] Running filter_problematic_tracks(threshold=10.0)")
                    filter_problematic_tracks(context, threshold=10.0)

                print("[GOOD_TRACKS][REBUILD] Triggered from execute() after filter/cleanup (Stage2)")
                self._rebuild_good_tracks(context, reason="Post-Stage2 cleanup")

                frame = find_first_weak_frame_solve(context)
                if frame is None:
                    print("[MASTER_CYCLE][INFO] No weak frame found after Stage2 cleanup – resolving camera.")
                    log_threshold_extrema(bpy.context.scene)
                    bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                    return {'FINISHED'}

                # Tracking-Defaults optional aktualisieren (nicht löschen!)
                print("[MASTER_CYCLE][INFO] Updating default tracking sizes.")
                update_default_sizes(context)

                # Cache-Keys bereinigen, aber nichts mehr überschreiben
                for k in ("frame_value_cache", "kaiserlich_best_thresholds"):
                    if k in scene:
                        if k.startswith("kaiserlich_best_thresholds"):
                            print(f"[BEST_TRACKS][CACHE][DELETE] Removing scene['{k}'] cache entry")
                        else:
                            print(f"[SCENE][CACHE][DELETE] Removing scene['{k}'] cache entry")
                        del scene[k]

            except Exception as ex:
                self.report({'ERROR'}, f"Error during filter process: {ex}")
                print(f"[MASTER_CYCLE][ERROR] Error during filter process: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # Frame setzen + Folgeoperator starten
        # ------------------------------------------------------------------
        scene.frame_current = frame
        print(f"[MASTER_CYCLE][INFO] Setting scene.frame_current to {frame}")

        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
                print(f"[MASTER_CYCLE][INFO] Updated space.clip_user.frame_current to {frame}")
        except Exception as e:
            print(f"[MASTER_CYCLE][WARN] Could not update clip_user.frame_current: {e}")
            pass

        print("[MASTER_CYCLE][INFO] Invoking master_detect_adapt.")
        bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')

        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
