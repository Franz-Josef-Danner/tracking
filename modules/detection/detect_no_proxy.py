"""Feature detection with proxy disabled."""

import bpy


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
    margin = int(margin)
    if min_distance is None:
        min_distance = clip.size[0] / 20
    min_distance = int(min_distance)

    message = (
        f"Detecting features with threshold={threshold}, "
        f"margin={margin}, min_distance={min_distance}"
    )
    if logger:
        logger.debug(message)
    else:
        print(message)

    # ensure proxies are disabled during detection
    clip.proxy.build_50 = False
    clip.use_proxy = False

    bpy.ops.clip.detect_features(
        threshold=threshold,
        margin=margin,
        min_distance=min_distance,
    )

__all__ = ["detect_features_no_proxy"]
