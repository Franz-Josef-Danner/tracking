import bpy
from ..helpers.delete_tracks import delete_selected_tracks
from ..helpers.utils import LAST_TRACK_END
from .error_value import calculate_clip_error
from .tracking.solver import detect_features_once, enable_proxy


def disable_proxy():
    """Disable proxies if possible."""
    if bpy.ops.clip.proxy_off.poll():
        bpy.ops.clip.proxy_off()


def track_full_clip():
    """Track the clip forward if possible."""
    if bpy.ops.clip.track_full.poll():
        bpy.ops.clip.track_full(silent=True)


def cleanup_all_tracks(clip):
    """Remove all tracks from the clip."""
    for t in clip.tracking.tracks:
        t.select = True
    delete_selected_tracks()


def run_iteration(context):
    """Execute one detection and tracking iteration."""
    clip = context.space_data.clip
    disable_proxy()
    detect_features_once()
    enable_proxy()
    track_full_clip()
    frames = LAST_TRACK_END if LAST_TRACK_END is not None else 0
    error_val = calculate_clip_error(clip)
    delete_selected_tracks()
    return frames, error_val


def _run_test_cycle(context, cleanup=False, cycles=4):
    """Run detection and tracking multiple times and return total frames and error."""
    clip = context.space_data.clip
    total_end = 0
    total_error = 0.0
    for i in range(cycles):
        print(f"[Test Cycle] Durchgang {i + 1}")
        frames, err = run_iteration(context)
        total_end += frames
        total_error += err
    if cleanup:
        cleanup_all_tracks(clip)
    print(f"[Test Cycle] Summe End-Frames: {total_end}, Error: {total_error:.4f}")
    return total_end, total_error


def run_pattern_size_test(context):
    """Execute a single cycle for the current pattern size with one tracking pass."""
    return _run_test_cycle(context, cleanup=True, cycles=1)


def evaluate_motion_models(context, models=None, cycles=2):
    """Return the best motion model along with its score and error."""
    if models is None:
        models = ['Loc', 'LocRot', 'LocScale', 'LocRotScale', 'Affine', 'Perspective']
    clip = context.space_data.clip
    settings = clip.tracking.settings
    best_model = settings.default_motion_model
    best_score = None
    best_error = None
    for model in models:
        settings.default_motion_model = model
        score, err = _run_test_cycle(context, cycles=cycles)
        print(f"[Test Motion] model={model} frames={score} error={err:.4f}")
        if best_score is None or score > best_score or (
            score == best_score and (best_error is None or err < best_error)
        ):
            best_score = score
            best_error = err
            best_model = model
    settings.default_motion_model = best_model
    return best_model, best_score, best_error


def evaluate_channel_combinations(context, combos=None, cycles=2):
    """Return the best RGB channel combination with its score and error."""
    if combos is None:
        combos = [
            (True, False, False),
            (True, True, False),
            (True, True, True),
            (False, True, False),
            (False, True, True),
            (False, False, True),
        ]
    clip = context.space_data.clip
    settings = clip.tracking.settings
    best_combo = (
        settings.use_default_red_channel,
        settings.use_default_green_channel,
        settings.use_default_blue_channel,
    )
    best_score = None
    best_error = None
    for combo in combos:
        r, g, b = combo
        settings.use_default_red_channel = r
        settings.use_default_green_channel = g
        settings.use_default_blue_channel = b
        score, err = _run_test_cycle(context, cycles=cycles)
        print(f"[Test Channel] combo={combo} frames={score} error={err:.4f}")
        if best_score is None or score > best_score or (
            score == best_score and (best_error is None or err < best_error)
        ):
            best_score = score
            best_error = err
            best_combo = combo
    (
        settings.use_default_red_channel,
        settings.use_default_green_channel,
        settings.use_default_blue_channel,
    ) = best_combo
    return best_combo, best_score, best_error


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
