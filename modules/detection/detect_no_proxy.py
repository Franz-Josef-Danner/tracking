"""Feature detection with proxy disabled."""

import time

import bpy
from ..proxy.proxy_wait import log_proxy_status


def detect_features_no_proxy(clip, threshold=1.0, margin=None, min_distance=None, logger=None):
    """Run :func:`bpy.ops.clip.detect_features` with proxies disabled.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        The movie clip on which to perform feature detection.
    threshold : float, optional
        Detection threshold, defaults to ``1.0``.
    margin : int, optional
        Margin value passed to the operator. If ``None`` it is derived from
        ``clip.size``.
    min_distance : int, optional
        Minimum distance between detected features. If ``None`` it is derived
        from ``clip.size``.
    logger : :class:`TrackerLogger`, optional
        Logger for debug output. When omitted ``print`` is used.
    """
    if margin is None:
        margin = clip.size[0] / 200
        if logger:
            logger.debug(f"Auto-calculated margin: {margin}")
    margin = int(margin)
    if min_distance is None:
        min_distance = clip.size[0] / 20
        if logger:
            logger.debug(f"Auto-calculated min_distance: {min_distance}")
    min_distance = int(min_distance)

    message = (
        f"Detecting features on {clip.name} with threshold={threshold}, "
        f"margin={margin}, min_distance={min_distance}"
    )
    if logger:
        logger.debug(message)
    else:
        print(message)

    # ensure proxies are disabled during detection
    clip.proxy.build_50 = False
    clip.use_proxy = False
    if logger:
        logger.debug("Proxies disabled for detection")
    from modules.proxy.proxy_wait import log_proxy_status
    log_proxy_status(clip)
    log_proxy_status(clip, logger)

    start_time = time.time()

    bpy.ops.clip.detect_features(
        "EXEC_DEFAULT",
        threshold=threshold,
        margin=margin,
        min_distance=min_distance,
    )
    duration = time.time() - start_time

    if logger:
        logger.debug(
            f"Detection finished in {duration:.2f}s, {len(clip.tracking.tracks)} markers present"
        )

__all__ = ["detect_features_no_proxy"]
