"""
playhead_helper
================

This module contains simple helper functions to retrieve and restore
the playhead (frame cursor) position in Blender’s Movie Clip Editor.
When calibrating motion model thresholds it is necessary to run
multiple tracking cycles starting from the same frame.  These helpers
encapsulate the logic for capturing the initial frame and resetting
both the scene and clip editor back to that frame.

Usage example::

    import bpy
    from .playhead_helper import get_start_frame, reset_to_frame

    start = get_start_frame(bpy.context)
    # run tracking here...
    reset_to_frame(bpy.context, start)

Note
----
The ``reset_to_frame`` function attempts to update all visible clip
editor spaces that are displaying the same clip as the active space in
order to maintain consistency across the UI.  If no clip is currently
active, only the scene frame will be updated.
"""

from __future__ import annotations

import bpy

def get_start_frame(context: bpy.types.Context) -> int:
    """Return the current frame of the scene (playhead position).

    Parameters
    ----------
    context : bpy.types.Context
        The Blender context from which to obtain the scene.

    Returns
    -------
    int
        The current frame index in the scene.
    """
    scene = context.scene
    return getattr(scene, "frame_current", 0)


def reset_to_frame(context: bpy.types.Context, frame: int) -> None:
    """Reset the playhead to the specified frame in the scene and clip editor.

    Parameters
    ----------
    context : bpy.types.Context
        The Blender context used to access the scene and spaces.
    frame : int
        The frame index to set as the current frame.

    Notes
    -----
    Blender maintains separate frame counters for the scene
    (``scene.frame_current``) and for each clip editor space
    (``space.clip_user.frame_current``).  To fully reset the playhead,
    both need to be updated.  This helper iterates over all CLIP_EDITOR
    areas in all windows and updates the frame for spaces that show the
    same clip as the active space (``context.space_data.clip``).  If no
    clip is active the helper falls back to updating only the scene.
    """
    scene = context.scene
    scene.frame_current = frame
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return
    # Iterate through all windows to find clip editor spaces.  This
    # approach mirrors the logic used in the tracking operator to locate
    # the CLIP_EDITOR for context override.
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            for space in area.spaces:
                if space.type != 'CLIP_EDITOR':
                    continue
                # Only update spaces displaying the same clip.  When the
                # clip property is None the space is considered
                # uninitialized; skip it in that case.
                if getattr(space, 'clip', None) == clip:
                    space.clip_user.frame_current = frame