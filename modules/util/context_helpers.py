"""Context helper utilities for Kaiserlich Tracksycle."""

from __future__ import annotations

import bpy


def get_clip_editor_override(ctx=None):
    """Return an override dictionary for Clip Editor operations.

    The returned mapping contains ``window``, ``area``, ``region`` and
    ``space_data`` when available so operators can run outside the UI
    context.  ``ctx`` defaults to :data:`bpy.context`.
    """
    ctx = ctx or bpy.context
    override = {}
    window = getattr(ctx, "window", None)
    if window:
        override["window"] = window
        screen = getattr(window, "screen", None)
    else:
        screen = getattr(ctx, "screen", None)
    if screen:
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                override["area"] = area
                for region in area.regions:
                    if region.type == "WINDOW":
                        override["region"] = region
                        break
                spaces = getattr(area, "spaces", None)
                if spaces:
                    try:
                        space_iter = list(spaces)
                    except TypeError:
                        space_iter = [spaces.active]
                    for space in space_iter:
                        if space.type == "CLIP_EDITOR":
                            override["space_data"] = space
                            break
                break
    return override
