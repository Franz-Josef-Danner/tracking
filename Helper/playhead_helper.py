from __future__ import annotations
import bpy
from .scene import get_scene_range as _get_scene_range  # nutzt Helper/scene.py


def _clamp_to_scene(context: bpy.types.Context, frame: int) -> int:
    """Clamp auf [scene.frame_start, scene.frame_end]."""
    start, end = _get_scene_range(context)
    f = int(frame)
    if f < start:
        return start
    if f > end:
        return end
    return f


def get_start_frame(context: bpy.types.Context) -> int:
    """Liefert die aktuelle Playhead-Position (geklemmt auf die Szenenrange)."""
    scene = context.scene
    current = int(getattr(scene, "frame_current", 0))
    return _clamp_to_scene(context, current)


def reset_to_frame(context: bpy.types.Context, frame: int) -> None:
    """Setzt Playhead auf den spezifizierten Frame (hart auf Szenenrange geklemmt)
    und synchronisiert alle sichtbaren CLIP_EDITOR-Spaces, die denselben Clip zeigen.
    """
    target = _clamp_to_scene(context, int(frame))

    scene = context.scene
    scene.frame_current = target

    # Aktiven Clip (falls vorhanden) ermitteln
    active_clip = getattr(getattr(context, "space_data", None), "clip", None)
    if active_clip is None:
        return  # kein Clip-Kontext: Szene reicht

    # Alle CLIP_EDITOR-Spaces, die denselben Clip zeigen, synchronisieren
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            for space in area.spaces:
                if space.type != "CLIP_EDITOR":
                    continue
                if getattr(space, "clip", None) == active_clip:
                    space.clip_user.frame_current = target
