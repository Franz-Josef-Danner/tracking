import bpy
from ..helpers.tracking_helpers import (
    run_pattern_size_test,
    evaluate_motion_models,
    evaluate_channel_combinations,
)
class CLIP_OT_test_motion(bpy.types.Operator):
    bl_idname = "clip.test_motion"
    bl_label = "Test Motion"
    bl_description = "Testet verschiedene Motion Models"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        motion_models = ['Loc', 'LocRot', 'LocScale', 'LocRotScale', 'Affine', 'Perspective']
        best_model, score, error_val = evaluate_motion_models(context, motion_models)
        context.scene.test_value = motion_models.index(best_model)
        print(
            f"[Test Motion] best_model={best_model} frames={score} error={error_val:.4f}"
        )
        self.report({'INFO'}, f"Best Motion Model: {best_model}")
        return {'FINISHED'}



operator_classes = (CLIP_OT_test_motion,)

