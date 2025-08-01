from .tracking_marker_basis_operator import TRACKING_OT_marker_basis_values
from .place_marker_operator import TRACKING_OT_place_marker
from .cleanup_tracks import CLIP_OT_cleanup_tracks
from .low_marker_frame_operator import CLIP_OT_low_marker_frame
from ..helpers.delete_tracks import delete_selected_tracks
from ..helpers.test_marker_base_operator import TRACKING_OT_test_marker_base
from .error_value_operator import CLIP_OT_error_value
from .proxy_builder import CLIP_OT_proxy_build
from .proxy_toggle_operators import (
    CLIP_OT_proxy_enable,
    CLIP_OT_proxy_disable,
)
from .marker_validierung import CLIP_OT_marker_valurierung
from ..ui.ui_helpers import CLIP_OT_marker_status_popup
from .bidirectional_tracking_operator import TRACKING_OT_bidirectional_tracking
from .track_default_settings import CLIP_OT_track_default_settings
from .test_track_default_operator import TRACK_OT_test_default
from .test_track_default_settings import TRACK_OT_test_combined
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
from ..helpers.cycle_motion_model import TRACKING_OT_cycle_motion_model
from ..helpers.set_tracking_channels import CLIP_OT_set_tracking_channels

operator_classes = (
    TRACKING_OT_marker_basis_values,
    TRACKING_OT_place_marker,
    CLIP_OT_cleanup_tracks,
    CLIP_OT_low_marker_frame,
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
    TRACKING_OT_cycle_motion_model,
    CLIP_OT_proxy_build,
    CLIP_OT_proxy_enable,
    CLIP_OT_proxy_disable,
    TRACKING_OT_bidirectional_tracking,
    CLIP_OT_track_default_settings,
    TRACK_OT_test_default,
    TRACK_OT_test_combined,
    CLIP_OT_marker_valurierung,
    CLIP_OT_marker_status_popup,
    CLIP_OT_set_tracking_channels,
)
