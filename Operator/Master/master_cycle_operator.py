import bpy
from bpy.types import Operator, Context

# ---- Helper Imports ---------------------------------------------------------
from ...Helper.low_marker_frame import find_first_weak_frame
from ...Helper.filter_all_tracks import filter_and_delete_all_tracks
from ...Helper.filter_tracks import filter_problematic_tracks
from ...Helper.update_default_sizes import update_default_sizes
from ...Helper.find_clip_editor_area import find_clip_editor_area


class KAISERLICHTRACKER_OT_master_cycle_operator(Operator):
    """Master Operator – Sets the playhead to the frame with the fewest active markers"""
    bl_idname = "kaiserlich_tracker.master_cycle_operator"
    bl_label = "Master Operator"
    bl_description = "Sets the playhead to the first frame with the lowest number of active markers"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------
    # Lokaler Helper: erstellt/erneuert den good_tracks String
    # ------------------------------------------------------------
    def _rebuild_good_tracks(self, context: Context, reason: str = ""):
        scene = context.scene
        for key in ("good_tracks", "best_tracks"):
            if key in scene:
                del scene[key]
                print(f"[MASTER CYCLE] {reason} – deleted existing '{key}'")

        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if clip and hasattr(clip, "tracking"):
            track_names = [t.name for t in clip.tracking.tracks]
            scene["good_tracks"] = track_names
            print(f"[MASTER CYCLE] {reason} – rebuilt 'good_tracks' with {len(track_names)} tracks")
            for n in track_names:
                print(f"   • {n}")
        else:
            scene["good_tracks"] = []
            print(f"[MASTER CYCLE] {reason} – WARNING: no clip/tracking; 'good_tracks' empty")

    # ------------------------------------------------------------
    # Hauptausführung
    # ------------------------------------------------------------
    def execute(self, context: Context):
        print("\n[MASTER CYCLE] --------------------------------------------")
        print("[MASTER CYCLE] Operator started")

        frame = find_first_weak_frame(context)
        scene = context.scene

        # ------------------------------------------------------------------
        # CLEANUP-ZWEIG – wenn kein schwacher Frame gefunden wird
        # ------------------------------------------------------------------
        if frame is None:
            print("[MASTER CYCLE] No weak frame found – starting cleanup")

            try:
                # ----------------------------------------------------------
                # Ensure valid CLIP_EDITOR context
                # ----------------------------------------------------------
                window, area, region, space = find_clip_editor_area(getattr(getattr(context, "space_data", None), "clip", None))
                if not all((window, area, region, space)):
                    raise RuntimeError("No CLIP_EDITOR area found – filter_tracks requires a valid context.")

                clip_ref = getattr(getattr(context, "space_data", None), "clip", None)
                if getattr(space, "clip", None) is None and clip_ref:
                    space.clip = clip_ref

                clip_obj = getattr(space, "clip", None)
                if clip_obj is None:
                    raise RuntimeError("No active clip in the current context.")

                # ------------------------------------------------------------------
                # Stage 1: Grobfilterung und Löschung
                # ------------------------------------------------------------------
                print("[MASTER CYCLE] Stage 1: filter_tracks (threshold=30.0)")
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    res = bpy.ops.clip.filter_tracks(track_threshold=30.0)
                    tracking = clip_obj.tracking
                    flagged_names = [t.name for t in tracking.tracks if t.select]
                    print(f"[MASTER CYCLE] Stage 1: {len(flagged_names)} tracks flagged")
                    if flagged_names:
                        from ...Helper.delete import delete_tracks_by_names
                        delete_tracks_by_names(bpy.context, flagged_names)
                        print("[MASTER CYCLE] Stage 1: flagged tracks deleted")

                # -> good_tracks nach Stage1
                self._rebuild_good_tracks(context, reason="Post-Stage1 cleanup")

                # ------------------------------------------------------------------
                # Stage 2: Feinkorrektur-Filter
                # ------------------------------------------------------------------
                print("[MASTER CYCLE] Stage 2: filter_problematic_tracks (threshold=10.0)")
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    try:
                        filter_problematic_tracks(context, threshold=10.0)
                    except Exception as e:
                        print(f"[MASTER CYCLE] Stage 2 WARNING: {e}")

                # -> good_tracks nach Stage2
                self._rebuild_good_tracks(context, reason="Post-Stage2 cleanup")

                # ------------------------------------------------------------------
                # Versuch erneut, schwachen Frame zu finden
                # ------------------------------------------------------------------
                frame = find_first_weak_frame(context)
                if frame is None:
                    # -> good_tracks auch vor Resolve
                    self._rebuild_good_tracks(context, reason="Pre-resolve cleanup checkpoint")
                    print("[MASTER CYCLE] No weak frame after cleanup – starting resolve")
                    bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                    return {'FINISHED'}

                # ------------------------------------------------------------------
                # Update default sizes, Cache-Reset
                # ------------------------------------------------------------------
                print("[MASTER CYCLE] Stage 3: update_default_sizes and cache reset")
                op, os, np, ns = update_default_sizes(context)

                reset_keys = ["frame_value_cache", "kaiserlich_best_thresholds"]
                for k in reset_keys:
                    if k in scene:
                        del scene[k]
                        print(f"[MASTER CYCLE] Cleared cache: {k}")

                # -> good_tracks nach Cache-Reset
                self._rebuild_good_tracks(context, reason="Post-cache-reset cleanup")

                # ------------------------------------------------------------------
                # Reset Threshold Properties
                # ------------------------------------------------------------------
                from ...Helper.util_scene import set_scene_props
                set_scene_props(
                    scene,
                    kaiserlich_rot_thresh_x=1.0,
                    kaiserlich_rot_thresh_y=1.0,
                    kaiserlich_scale_thresh_min=1.0,
                    kaiserlich_scale_thresh_max=1.1,
                    kaiserlich_rot_scale_thresh_rot=1.0,
                    kaiserlich_rot_scale_thresh_scale=1.0,
                    kaiserlich_perspective_thresh=1.0
                )
                print("[MASTER CYCLE] Threshold properties reset")

            except Exception as ex:
                print(f"[MASTER CYCLE] ERROR during cleanup: {ex}")
                self.report({'ERROR'}, f"Error during filter process: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # NORMALZWEIG – wenn schwacher Frame gefunden wurde
        # ------------------------------------------------------------------
        print(f"[MASTER CYCLE] Weak frame found: {frame}")
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Trigger Deep Test Operator
        # ------------------------------------------------------------------
        try:
            print("[MASTER CYCLE] Triggering Deep Test Operator...")
            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception as e:
            print(f"[MASTER CYCLE] WARNING: Could not trigger Deep Test Operator: {e}")

        print("[MASTER CYCLE] Operator finished successfully")
        print("------------------------------------------------------------\n")
        return {'FINISHED'}


# ---- Registration ----------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
