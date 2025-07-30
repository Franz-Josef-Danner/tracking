from .tracking_marker_basis_operator import TRACKING_OT_marker_basis_values
from .place_marker_operator import TRACKING_OT_place_marker
from .cleanup_operator import CLIP_OT_cleanup_tracks

operator_classes = (
    TRACKING_OT_marker_basis_values,
    TRACKING_OT_place_marker,
    CLIP_OT_cleanup_tracks,
)
