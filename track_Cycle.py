import bpy
import logging
from proxy_switch import ToggleProxyOperator
from track_length import delete_short_tracks_with_prefix

logger = logging.getLogger(__name__)


def run(context):
    """Example callback executed after detection.

    It toggles proxy/timecode on the current clip to ensure proxies are
    enabled before starting another tracking cycle.
    """
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None)
    if clip is None:
        clip = getattr(context.scene, "clip", None)

    if clip and not clip.use_proxy:
        bpy.ops.clip.toggle_proxy()
        logger.info("Proxy/Timecode aktiviert")
    else:
        logger.info("Proxy bereits aktiv oder kein Clip")

    # Run bidirectional tracking on TRACK_ markers
    bpy.ops.clip.auto_track_bidir()

    # Delete short tracks with the TRACK_ prefix
    delete_short_tracks_with_prefix(context)

