import bpy
from .feature_detection import find_next_low_marker_frame as _find_next_low_marker_frame
from .set_playhead_to_frame import set_playhead_to_frame


def find_next_low_marker_frame(context=None):
    """Find and jump to the next frame with too few markers."""
    if context is None:
        context = bpy.context
    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("\u26A0\uFE0F Kein aktiver Movie Clip gefunden.")
        return None, 0
    frame, count = _find_next_low_marker_frame(scene, clip, scene.marker_frame)
    if frame is not None:
        set_playhead_to_frame(scene, frame)
    return frame, count


def set_playhead_to_frame_from_ui(context=None):
    """Set playhead using the UI value ``scene.marker_frame``."""
    if context is None:
        context = bpy.context
    scene = context.scene
    set_playhead_to_frame(scene, scene.marker_frame)


__all__ = ["find_next_low_marker_frame", "set_playhead_to_frame_from_ui"]
