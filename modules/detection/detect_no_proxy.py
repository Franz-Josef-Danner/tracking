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

    Returns
    -------
    bool
        ``True`` if detection was executed successfully, ``False`` otherwise.
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
    log_proxy_status(clip, logger)

    before = len(clip.tracking.tracks)
    start_time = time.time()
    for area in bpy.context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    override = {
                        'area': area,
                        'region': region,
                        'scene': bpy.context.scene,
                        'clip': clip,
                    }
                    try:
                        with bpy.context.temp_override(**override):
                            result = bpy.ops.clip.detect_features(
                                threshold=threshold,
                                margin=margin,
                                min_distance=min_distance,
                            )
                    except Exception as exc:  # pylint: disable=broad-except
                        if logger:
                            logger.error(
                                f"detect_features operator failed: {exc}"
                            )
                        return False
                    break
            break
    else:
        if logger:
            logger.error("\u274c Kein aktiver Movie Clip Editor gefunden.")
        return False
    duration = time.time() - start_time
    after = len(clip.tracking.tracks)

    if logger:
        logger.debug(
            f"Detection executed in {duration:.2f}s: {result}"
        )
        logger.info(
            f"Markers before: {before}, after: {after}, added: {after - before}"
        )
        logger.debug("End of detection step, handing results back")

    else:
        print(
            f"Detection executed in {duration:.2f}s: {result}. "
            f"Markers before: {before}, after: {after}, added: {after - before}"
        )

    return True

__all__ = ["detect_features_no_proxy"]
