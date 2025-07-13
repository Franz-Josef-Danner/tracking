import bpy
import logging
from .proxy_switch import ToggleProxyOperator
from .track_length import delete_short_tracks_with_prefix
from .few_marker_frame import set_playhead_to_low_marker_frame
from .utils import get_active_clip

logger = logging.getLogger(__name__)


def run(context):
    """Example callback executed after detection.

    It toggles proxy/timecode on the current clip to ensure proxies are
    enabled before starting another tracking cycle.
    """
    clip = get_active_clip(context)

    if clip and not clip.use_proxy:
        bpy.ops.clip.toggle_proxy()
        logger.info("Proxy/Timecode aktiviert")
    else:
        logger.info("Proxy bereits aktiv oder kein Clip")

    # Run bidirectional tracking on TRACK_ markers
    bpy.ops.clip.auto_track_bidir()

    # Delete short tracks with the TRACK_ prefix
    delete_short_tracks_with_prefix(context)

    # Position playhead on the first frame with too few markers
    set_playhead_to_low_marker_frame(context.scene.min_marker_count)

