from .tracking_marker_basis_operator import TRACKING_OT_marker_basis_values
from .place_marker_operator import TRACKING_OT_place_marker
from .cleanup_operator import CLIP_OT_cleanup_tracks
from .test_marker_base_operator import TRACKING_OT_test_marker_base
from .error_value_operator import CLIP_OT_error_value

operator_classes = (
    TRACKING_OT_marker_basis_values,
    TRACKING_OT_place_marker,
    CLIP_OT_cleanup_tracks,
    TRACKING_OT_test_marker_base,
    CLIP_OT_error_value,
)
