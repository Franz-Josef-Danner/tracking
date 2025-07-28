import bpy
from ...helpers.utils import update_frame_display


def set_playhead_to_frame(scene, frame: int):
    """Move the scene playhead to ``frame`` and update the display."""
    scene.frame_current = frame
    update_frame_display()
