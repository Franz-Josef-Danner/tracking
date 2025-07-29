# Expose helper functions via relative import
try:
    import bpy  # type: ignore
except ModuleNotFoundError:
    bpy = None

from .feature_math import (
    calculate_base_values,
    apply_threshold_to_margin_and_distance,
    marker_target_aggressive,
    marker_target_conservative,
)
from .step_order import extract_step_sequence_from_cycle

if bpy is not None:
    from .utils import *
    from .delete_selected_tracks import delete_selected_tracks
    from .select_short_tracks import select_short_tracks
    from .detection_helpers import (
        find_next_low_marker_frame,
        find_low_marker_frame,
        jump_to_first_frame_with_few_active_markers,
        detect_features_once,
        detect_features_main,
        detect_features_test,
    )
    from .proxy_helpers import enable_proxy, disable_proxy
    from .marker_helpers import (
        has_active_marker,
        get_undertracked_markers,
        select_tracks_by_names,
        select_tracks_by_prefix,
        ensure_valid_selection,
        cleanup_all_tracks,
    )
    from .tracking_helpers import (
        track_markers_range,
        _update_nf_and_motion_model,
        track_full_clip,
        run_iteration,
        _run_test_cycle,
        run_pattern_size_test,
        evaluate_motion_models,
        evaluate_channel_combinations,
    )
    from .set_playhead_to_frame import set_playhead_to_frame

