import bpy
from .utils import (
    update_frame_display,
    NF,
    pattern_limits,
    clamp_pattern_size,
    cycle_motion_model,
    DEFAULT_MARKER_FRAME,
    DEFAULT_MOTION_MODEL,
    LAST_TRACK_END,
)
from .detection_helpers import detect_features_once
from .proxy_helpers import enable_proxy, disable_proxy
from .delete_selected_tracks import delete_selected_tracks
from .marker_helpers import cleanup_all_tracks


def track_markers_range(scene, start, end, current, backwards):
    """Run clip.track_markers for ``start`` to ``end``."""
    scene.frame_start = start
    scene.frame_end = end
    if not backwards:
        scene.frame_current = current
        update_frame_display()
    bpy.ops.clip.track_markers(backwards=backwards, sequence=True)


def _update_nf_and_motion_model(frame, clip):
    """Maintain NF list and adjust motion model and pattern size."""
    global NF
    settings = clip.tracking.settings
    scene = bpy.context.scene
    min_size, max_size = pattern_limits(clip)
    if frame in NF:
        cycle_motion_model(settings, clip, reset_size=False)
        if settings.default_pattern_size < max_size:
            settings.default_pattern_size = min(
                int(settings.default_pattern_size * 1.1),
                max_size,
            )
            max_mf = DEFAULT_MARKER_FRAME * 2
            scene.marker_frame = min(int(scene.marker_frame * 1.1), max_mf)
    else:
        NF.append(frame)
        settings.default_motion_model = DEFAULT_MOTION_MODEL
        settings.default_pattern_size = int(settings.default_pattern_size * 0.9)
        if settings.default_pattern_size < max_size and scene.marker_frame > DEFAULT_MARKER_FRAME:
            scene.marker_frame = max(int(scene.marker_frame * 0.9), DEFAULT_MARKER_FRAME)
    settings.default_pattern_size = clamp_pattern_size(settings.default_pattern_size, clip)
    settings.default_search_size = settings.default_pattern_size * 2


def track_full_clip():
    """Track the clip forward if possible."""
    if bpy.ops.clip.track_full.poll():
        bpy.ops.clip.track_full(silent=True)


def run_iteration(context):
    """Execute one detection and tracking iteration."""
    clip = context.space_data.clip
    disable_proxy()
    detect_features_once()
    enable_proxy()
    track_full_clip()
    frames = LAST_TRACK_END if LAST_TRACK_END is not None else 0
    from ..operators.error_value import calculate_clip_error
    error_val = calculate_clip_error(clip)
    delete_selected_tracks()
    return frames, error_val


def _run_test_cycle(context, cleanup=False, cycles=4):
    """Run detection and tracking multiple times and return total frames and error."""
    clip = context.space_data.clip
    total_end = 0
    total_error = 0.0
    for _ in range(cycles):
        frames, err = run_iteration(context)
        total_end += frames
        total_error += err
    if cleanup:
        cleanup_all_tracks(clip)
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
