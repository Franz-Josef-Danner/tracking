"""Utility: reliably move playhead and update UI."""

import bpy


def set_playhead(frame, retries=2):
    """Position the playhead reliably at ``frame`` and refresh the UI."""

    if frame is None:
        return

    scene = bpy.context.scene
    for _ in range(retries):
        scene.frame_set(frame)
        if scene.frame_current == frame:
            break
        scene.frame_current = frame
        if scene.frame_current == frame:
            break
    else:
        pass

    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                area.tag_redraw()

