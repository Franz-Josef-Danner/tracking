"""Wrapper utilities for clip tracking."""

import bpy


def track_markers(context, forwards=True, backwards=True):
    """Track markers in both directions based on arguments."""
    if forwards:
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
    if backwards:
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)

