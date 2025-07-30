import bpy
from ..operators.tracking.solver import detect_features_once, enable_proxy
from .error_value_operator import calculate_clip_error
from .track_full_clip import track_full_clip
from .delete_tracks import delete_selected_tracks
from .utils import LAST_TRACK_END


def _disable_proxy():
    if bpy.ops.clip.proxy_off.poll():
        bpy.ops.clip.proxy_off()


def run_iteration(context):
    """Execute one detection and tracking iteration."""
    clip = context.space_data.clip
    _disable_proxy()
    detect_features_once()
    enable_proxy()
    track_full_clip()
    frames = LAST_TRACK_END if LAST_TRACK_END is not None else 0
    error_val = calculate_clip_error(clip)
    delete_selected_tracks()
    return frames, error_val
