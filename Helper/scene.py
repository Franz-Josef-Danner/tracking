import bpy
from typing import Tuple


def get_scene_range(context: bpy.types.Context) -> Tuple[int, int]:
    """Gibt (frame_start, frame_end) der aktiven Szene zurück.
    Defensive Korrektur, falls End < Start gesetzt wurde."""
    scene = context.scene
    start = int(getattr(scene, "frame_start", 1))
    end = int(getattr(scene, "frame_end", start))
    if end < start:
        end = start
    return start, end


def get_start_frame(context: bpy.types.Context) -> int:
    """Startframe der aktiven Szene."""
    start, _ = get_scene_range(context)
    return start


def get_end_frame(context: bpy.types.Context) -> int:
    """Endframe der aktiven Szene."""
    _, end = get_scene_range(context)
    return end
