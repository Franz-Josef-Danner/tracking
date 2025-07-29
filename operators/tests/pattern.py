import bpy
from ...helpers.tracking_helpers import (
    run_pattern_size_test,
    evaluate_motion_models,
    evaluate_channel_combinations,
)
class CLIP_OT_test_pattern(bpy.types.Operator):
    bl_idname = "clip.test_pattern"
    bl_label = "Test Pattern"
    bl_description = "Testet verschiedene Pattern-Gr\u00f6\u00dfen"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        settings = clip.tracking.settings
        best_size = settings.default_pattern_size
        best_score = None
        best_error = None
        min_error = None
        last_score = None
        drops_left = 0
        while True:
            score, error_sum = run_pattern_size_test(context)
            print(
                f"[Test Pattern] size={settings.default_pattern_size} frames={score} error={error_sum:.4f}"
            )
            if best_score is None or score > best_score or (
                score == best_score and (best_error is None or error_sum < best_error)
            ):
                best_score = score
                best_error = error_sum
                best_size = settings.default_pattern_size
            if min_error is None or error_sum < min_error:
                min_error = error_sum
            if last_score is not None:
                if score == last_score and error_sum > min_error * 1.1:
                    break
                if drops_left > 0:
                    if score > last_score:
                        drops_left = 0
                    else:
                        drops_left -= 1
                        if drops_left == 0:
                            break
                elif score < last_score:
                    drops_left = 4
            last_score = score
            if bpy.ops.clip.pattern_up.poll():
                bpy.ops.clip.pattern_up()
            else:
                break
        settings.default_pattern_size = best_size
        settings.default_search_size = best_size * 2
        context.scene.test_value = best_size
        print(
            f"[Test Pattern] best_size={best_size} frames={best_score} error={best_error:.4f}"
        )
        self.report({'INFO'}, f"Best Pattern Size: {best_size}")
        return {'FINISHED'}



operator_classes = (CLIP_OT_test_pattern,)

