from .tracking_marker_basis_operator import TRACKING_OT_marker_basis_values
from .place_marker_operator import TRACKING_OT_place_marker
from .cleanup_operator import CLIP_OT_cleanup_tracks
from ..helpers.test_marker_base_operator import TRACKING_OT_test_marker_base
from .error_value_operator import CLIP_OT_error_value
from .proxy_builder import CLIP_OT_proxy_build
from .proxy_toggle_operators import (
    CLIP_OT_proxy_enable,
    CLIP_OT_proxy_disable,
)
from .test_panel_operators import (
    TRACKING_OT_test_cycle,
    TRACKING_OT_test_base,
    TRACKING_OT_test_place_marker,
    TRACKING_OT_test_track_markers,
    TRACKING_OT_test_error_value,
    TRACKING_OT_test_tracking_lengths,
    TRACKING_OT_test_cycle_motion,
    TRACKING_OT_test_tracking_channels,
)

operator_classes = (
    TRACKING_OT_marker_basis_values,
    TRACKING_OT_place_marker,
    CLIP_OT_cleanup_tracks,
    TRACKING_OT_test_marker_base,
    CLIP_OT_error_value,
    TRACKING_OT_test_cycle,
    TRACKING_OT_test_base,
    TRACKING_OT_test_place_marker,
    TRACKING_OT_test_track_markers,
    TRACKING_OT_test_error_value,
    TRACKING_OT_test_tracking_lengths,
    TRACKING_OT_test_cycle_motion,
    TRACKING_OT_test_tracking_channels,
    CLIP_OT_proxy_build,
    CLIP_OT_proxy_enable,
    CLIP_OT_proxy_disable,
)
