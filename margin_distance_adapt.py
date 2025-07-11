"""Utility helpers for margin and distance values.

The function :func:`ensure_margin_distance` ensures that the active clip has
``MARGIN`` and ``DISTANCE`` properties and returns them scaled by the given
threshold. The base distance is also returned unchanged.
"""

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
    print(
        f"ensure_margin_distance: threshold={threshold:.4f}, "
        f"base_distance={base_distance}, margin={margin}, distance={distance}"
    )
    return margin, distance, base_distance

