"""Feature detection with proxy disabled."""

import bpy


def detect_features_no_proxy(clip, threshold=1.0, margin=None, distance=None):
    """Run :func:`bpy.ops.clip.detect_features` with proxies disabled.

    Parameters
    ----------
    clip : :class:`bpy.types.MovieClip`
        The movie clip on which to perform feature detection.
    threshold : float, optional
        Detection threshold, defaults to ``1.0``.
    margin : float, optional
        Margin value passed to the operator. If ``None`` it is derived from
        ``clip.size``.
    distance : float, optional
        Minimum distance between detected features. If ``None`` it is derived
        from ``clip.size``.
    """
    if margin is None:
        margin = clip.size[0] / 200
    if distance is None:
        distance = clip.size[0] / 20

    # ensure proxies are disabled during detection
    clip.proxy.build_50 = False
    clip.use_proxy = False

    bpy.ops.clip.detect_features(
        threshold=threshold,
        margin=margin,
        distance=distance,
    )

__all__ = ["detect_features_no_proxy"]
