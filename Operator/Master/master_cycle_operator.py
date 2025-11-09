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
        frame = find_first_weak_frame(context)

        # ------------------------------------------------------------------
        # If no weak frame is found → perform cleanup and proceed
        # ------------------------------------------------------------------
        if frame is None:
            try:
                # ----------------------------------------------------------
                # Ensure a valid CLIP_EDITOR context
                # ----------------------------------------------------------
                window, area, region, space = find_clip_editor_area(getattr(getattr(context, "space_data", None), "clip", None))
                if window is None or area is None or region is None or space is None:
                    raise RuntimeError("No CLIP_EDITOR area found – filter_tracks requires a valid context.")

                clip_ref = getattr(getattr(context, "space_data", None), "clip", None)

                # Make sure space.clip is properly set
                if getattr(space, "clip", None) is None and clip_ref:
                    try:
                        space.clip = clip_ref
                    except Exception:
                        pass

                clip_obj = getattr(space, "clip", None)
                if clip_obj is None:
                    raise RuntimeError("No active clip in the current context.")

                # ------------------------------------------------------------------
                # Stage 1: Filter and delete problematic tracks
                # ------------------------------------------------------------------
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    res = bpy.ops.clip.filter_tracks(track_threshold=30.0)
                    tracking = clip_obj.tracking
                    flagged_names = [t.name for t in tracking.tracks if t.select]
                    if flagged_names:
                        from ...Helper.delete import delete_tracks_by_names
                        _ = delete_tracks_by_names(bpy.context, flagged_names)

                # ------------------------------------------------------------------
                # Stage 2: Secondary filtering step
                # ------------------------------------------------------------------
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    try:
                        filter_problematic_tracks(context, threshold=10.0)
                    except Exception:
                        pass

                # ------------------------------------------------------------------
                # Retry finding a weak frame
                # ------------------------------------------------------------------
                frame = find_first_weak_frame(context)
                if frame is None:
                    try:
                        op_id_resolve = "kaiserlich_tracker.master_resolve_operator"
                        op_cls = bpy.ops
                        if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_resolve_operator"):
                            msg = f"Operator '{op_id_resolve}' not registered. Check bl_idname in Operator/Master/master_resolve_operator.py"
                            self.report({'ERROR'}, msg)
                            return {'CANCELLED'}

                        bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                        return {'FINISHED'}

                    except Exception as resolve_err:
                        self.report({'ERROR'}, f"Error while starting the resolve operator: {resolve_err}")
                        return {'CANCELLED'}

                # ------------------------------------------------------------------
                # If a new weak frame was found after cleanup
                # ------------------------------------------------------------------
                try:
                    op, os, np, ns = update_default_sizes(context)

                    # --------------------------------------------------------------
                    # Reset internal caches (min_distance_values bleibt erhalten)
                    # --------------------------------------------------------------
                    scene = context.scene
                    reset_keys = ["frame_value_cache", "kaiserlich_best_thresholds"]
                    for k in reset_keys:
                        if k in scene:
                            del scene[k]

                    # --------------------------------------------------------------
                    # Store all current track names in scene["good_tracks"]
                    # --------------------------------------------------------------
                    try:
                        if "good_tracks" in scene:
                            del scene["good_tracks"]

                        clip = getattr(context.space_data, "clip", None)
                        if clip and hasattr(clip, "tracking"):
                            track_names = [t.name for t in clip.tracking.tracks]
                            scene["good_tracks"] = track_names
                        else:
                            scene["good_tracks"] = []
                    except Exception as e:
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
                except ValueError:
                    pass

            except Exception as ex:
                self.report({'ERROR'}, f"Error during filter process: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # If a weak frame was found → set playhead to that frame
        # ------------------------------------------------------------------
        scene = context.scene
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
        op_id = "kaiserlichtracker.master_deep_test_operator"
        try:
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_deep_test_operator"):
                msg = f"Operator '{op_id}' not registered. Check bl_idname in Operator/Master/master_deep_test_operator.py"
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Compute and update track quality metrics
        # ------------------------------------------------------------------
        try:
            from ...Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            quality_percent = float(metrics.get("prozent", 100.0))
            context.scene.kaiserlich_quality_percent = f"{int(round(quality_percent))}%"

            # Refresh the UI
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()

        except Exception:
            quality_percent = 100.0

        # ------------------------------------------------------------------
        # Compute marker progress
        # ------------------------------------------------------------------
        try:
            from ...Helper.frame_track_progress import compute_marker_progress
            value, perc = compute_marker_progress(context.scene, update_ui=True)
        except Exception:
            pass

        return {'FINISHED'}


# ---- Registration ----------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)