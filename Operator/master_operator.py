# Operator/master_operator.py
import bpy
from bpy.types import Operator, Context

# ---- Helper Imports ---------------------------------------------------------
from ..Helper.low_marker_frame import find_first_weak_frame
from ..Helper.bootstrap import run_bootstrap  # <--- Import Bootstrap helper


class KAISERLICHTRACKER_OT_master_operator(Operator):
    """Starts a sequence of all functions to perform an optimized process for generating an ideal camera solve (time-consuming)."""
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "Master Operator"
    bl_description = (
        "Starts a sequence of all functions to perform an optimized process for generating an ideal camera solve (time-consuming)."
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        # ------------------------------------------------------------------
        # Run bootstrap to calculate initial parameters
        # ------------------------------------------------------------------
        scene = context.scene
        ef_target = int(getattr(scene, "kaiserlich_markers_per_frame", 25))
        params = run_bootstrap(context, ef_target)
        if params:
            scene["bootstrap_params"] = params

        # ------------------------------------------------------------------
        # Determine the first frame with the lowest marker count
        # ------------------------------------------------------------------
        frame = find_first_weak_frame(context)

        # ------------------------------------------------------------------
        # If no frame is found → finish normally
        # ------------------------------------------------------------------
        if frame is None:
            return {'FINISHED'}

        # ------------------------------------------------------------------
        # If a frame is found → move the playhead and start DeepTest
        # ------------------------------------------------------------------
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Execute DeepTest operator
        # Expected ID: bl_idname = "kaiserlich_tracker.master_deep_test_operator"
        # ------------------------------------------------------------------
        op_id = "kaiserlich_tracker.master_deep_test_operator"
        try:
            # Sanity check: is the operator registered?
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_deep_test_operator"):
                msg = f"Operator '{op_id}' not registered. Check bl_idname in Operator/Master/master_deep_test_operator.py"
                return {'CANCELLED'}

            # Start DeepTest
            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception as ex:
            pass

        # ------------------------------------------------------------------
        # 🧮 Final: compute marker progress and store result in scene properties
        # ------------------------------------------------------------------
        try:
            from ..Helper.frame_track_progress import compute_marker_progress
            value, perc = compute_marker_progress(context.scene, update_ui=True)
        except Exception as progress_err:
            pass

        # ------------------------------------------------------------------
        # Compute track quality metrics and update UI percentage value
        # ------------------------------------------------------------------
        try:
            from ..Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            percent = f"{int(round(metrics['prozent']))}%"
            context.scene.kaiserlich_quality_percent = percent

            # Force UI refresh
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()
        except Exception:
            pass

        return {'FINISHED'}


# ---- Registration -----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_operator)