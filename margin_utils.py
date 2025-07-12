"""Utilities for margin and distance values used in feature detection."""

import bpy
import math


def compute_margin_distance():
    """Store margin and distance properties on the active clip."""
    area = next((a for a in bpy.context.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if not area:
        print("Movie Clip Editor nicht aktiv.")
        return
    space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
    if not space or not space.clip:
        print("Kein Clip im Movie Clip Editor geladen.")
        return

    clip = space.clip
    width = clip.size[0]
    margin = width / 200
    distance = width / 20
    clip["MARGIN"] = margin
    clip["DISTANCE"] = distance
    print(f"Breite: {width}")
    print(f"MARGIN (Breite / 200): {margin}")
    print(f"DISTANCE (Breite / 20): {distance}")


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
