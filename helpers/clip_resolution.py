import bpy
from .marker_targeting import calculate_base_values


def calculate_base_values_from_clip(context=None, clip=None):
    """Liest Clip-Aufl\u00f6sung aus und berechnet margin_base + min_distance_base."""
    if context is None:
        context = bpy.context
    if clip is None:
        clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("\u26a0\ufe0f Kein aktiver Movie Clip gefunden.")
        return 0, 0
    width, _ = clip.size
    return calculate_base_values(width)
