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

    def execute(self, context: Context):
        print("\n[MASTER CYCLE] --------------------------------------------")
        print("[MASTER CYCLE] Operator started")

        frame = find_first_weak_frame(context)
        scene = context.scene

        # ------------------------------------------------------------------
        # If no weak frame is found → perform cleanup and proceed
        # ------------------------------------------------------------------
        if frame is None:
            print("[MASTER CYCLE] No weak frame found – starting cleanup and good_tracks generation")

            try:
                # ----------------------------------------------------------
                # Ensure a valid CLIP_EDITOR context
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

                print("[MASTER CYCLE] Stage 1: Running filter_tracks (threshold=30.0)")
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    res = bpy.ops.clip.filter_tracks(track_threshold=30.0)
                    tracking = clip_obj.tracking
                    flagged_names = [t.name for t in tracking.tracks if t.select]
                    print(f"[MASTER CYCLE] Stage 1: {len(flagged_names)} tracks flagged for deletion")

                    if flagged_names:
                        from ...Helper.delete import delete_tracks_by_names
                        delete_tracks_by_names(bpy.context, flagged_names)
                        print("[MASTER CYCLE] Stage 1: Flagged tracks deleted successfully")

                print("[MASTER CYCLE] Stage 2: Running filter_problematic_tracks (threshold=10.0)")
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    try:
                        filter_problematic_tracks(context, threshold=10.0)
                    except Exception as e:
                        print(f"[MASTER CYCLE] Stage 2 WARNING: {e}")

                # ------------------------------------------------------------------
                # Retry finding a weak frame
                # ------------------------------------------------------------------
                frame = find_first_weak_frame(context)
                if frame is None:
                    print("[MASTER CYCLE] No weak frame found after filtering – starting resolve operator")
                    try:
                        bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                        return {'FINISHED'}
                    except Exception as resolve_err:
                        self.report({'ERROR'}, f"Error while starting the resolve operator: {resolve_err}")
                        return {'CANCELLED'}

                # ------------------------------------------------------------------
                # Update sizes, reset caches, and create track strings
                # ------------------------------------------------------------------
                print("[MASTER CYCLE] Stage 3: Updating default sizes")
                op, os, np, ns = update_default_sizes(context)

                # Reset caches
                reset_keys = ["frame_value_cache", "kaiserlich_best_thresholds"]
                for k in reset_keys:
                    if k in scene:
                        del scene[k]
                        print(f"[MASTER CYCLE] Cleared scene cache: {k}")

                # --------------------------------------------------------------
                # Manage 'good_tracks' and 'best_tracks'
                # --------------------------------------------------------------
                print("[MASTER CYCLE] Stage 4: Preparing to store 'good_tracks'")
                for key in ("good_tracks", "best_tracks"):
                    if key in scene:
                        del scene[key]
                        print(f"[MASTER CYCLE] Existing '{key}' string deleted")

                try:
                    clip = getattr(context.space_data, "clip", None)
                    if clip and hasattr(clip, "tracking"):
                        track_names = [t.name for t in clip.tracking.tracks]
                        scene["good_tracks"] = track_names
                        print(f"[MASTER CYCLE] 'good_tracks' created with {len(track_names)} track names:")
                        for name in track_names:
                            print(f"   • {name}")
                    else:
                        scene["good_tracks"] = []
                        print("[MASTER CYCLE] WARNING: No clip or tracking data found – 'good_tracks' is empty")

                except Exception as e:
                    print(f"[MASTER CYCLE] ERROR while storing 'good_tracks': {e}")
                    self.report({'WARNING'}, f"Could not store track names: {e}")

                # --------------------------------------------------------------
                # Reset threshold properties
                # --------------------------------------------------------------
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
                print("[MASTER CYCLE] Threshold properties reset successfully")

            except Exception as ex:
                print(f"[MASTER CYCLE] ERROR during cleanup: {ex}")
                self.report({'ERROR'}, f"Error during filter process: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # If a weak frame was found → set playhead
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
        # Trigger next operator (Deep Test)
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
