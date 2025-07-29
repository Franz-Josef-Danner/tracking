import bpy
from .pattern import CLIP_OT_test_pattern
from .motion import CLIP_OT_test_motion
from ...helpers.tracking_helpers import (
    run_pattern_size_test,
    evaluate_motion_models,
    evaluate_channel_combinations,
)
class CLIP_OT_test_channel(bpy.types.Operator):
    bl_idname = "clip.test_channel"
    bl_label = "Test Channel"
    bl_description = "Testet verschiedene Farbkanal-Kombinationen"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        combos = [
            (True, False, False),
            (True, True, False),
            (True, True, True),
            (False, True, False),
            (False, True, True),
            (False, False, True),
        ]
        best_combo, score, error_val = evaluate_channel_combinations(context, combos)
        context.scene.test_value = combos.index(best_combo)
        print(
            f"[Test Channel] best_combo={best_combo} frames={score} error={error_val:.4f}"
        )
        self.report({'INFO'}, "Beste Kanal-Einstellung gewählt")
        return {'FINISHED'}


operator_classes = (
    CLIP_OT_test_pattern,
    CLIP_OT_test_motion,
    CLIP_OT_test_channel,
)

