import bpy
from .utils import update_frame_display


def set_playhead_to_frame(scene, frame: int):
    """Move the scene playhead to ``frame`` and update the display.

    Called by operators like :class:`~operators.tracking.detect.CLIP_OT_detect_button`
    and :class:`~operators.tracking.cleanup.CLIP_OT_track_cleanup`.
    """
    scene.frame_current = frame
    update_frame_display()
