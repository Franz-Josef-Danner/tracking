"""Utility: compute margin and distance values from threshold."""

import math


def ensure_margin_distance(clip, threshold=1.0):
    """Return margin and distance scaled by ``threshold`` along with the base distance."""

    if "MARGIN" not in clip or "DISTANCE" not in clip:
        width = clip.size[0]
        clip["MARGIN"] = max(1, int(width / 200))
        clip["DISTANCE"] = max(1, int(width / 20))

    base_margin = int(clip["MARGIN"])
    base_distance = int(clip["DISTANCE"])

    scale = math.log10(threshold * 100000) / 5
    margin = max(1, int(base_margin * scale))
    distance = max(1, int(base_distance * scale))
    return margin, distance, base_distance

