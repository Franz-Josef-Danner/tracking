"""Utilities for manipulating the playhead."""

import bpy


def set_playhead(frame):
    """Set the current frame to `frame`."""
    bpy.context.scene.frame_current = frame

