from .marker_helper_main import CLIP_OT_marker_helper_main
from .disable_proxy import CLIP_OT_disable_proxy
from .enable_proxy import CLIP_OT_enable_proxy
from .select_short_tracks import select_short_tracks
from .delete_selected_markers import delete_selected_markers

operator_classes = (
    marker_helper_main,
    enable_proxy,
    disable_proxy,
    select_short_tracks,
    delete_selected_markers,
)
