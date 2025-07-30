import bpy
from .marker_targeting import marker_target_conservative


def calculate_marker_target_from_ui(context=None):
    """Holt marker_basis aus Szene-UI und berechnet marker_plus usw."""
    if context is None:
        context = bpy.context
    frame = getattr(context.scene, "marker_frame", 0)
    return marker_target_conservative(frame)
