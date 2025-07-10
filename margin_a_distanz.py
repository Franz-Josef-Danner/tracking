"""Compute detection margin and distance values for the active clip."""

import bpy


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
    margin = width / 100
    distance = width / 20
    clip["MARGIN"] = margin
    clip["DISTANCE"] = distance
    print(f"Breite: {width}")
    print(f"MARGIN (Breite / 100): {margin}")
    print(f"DISTANCE (Breite / 20): {distance}")
