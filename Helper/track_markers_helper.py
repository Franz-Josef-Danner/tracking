import bpy
from typing import Optional

def track_markers_with_override(
    window: bpy.types.Window,
    area: bpy.types.Area,
    region: bpy.types.Region,
    space: bpy.types.SpaceClipEditor,
    backwards: bool = False,
    sequence: bool = False
) -> bool:
    """
    Führt ein Tracking mit Context Override aus.
    Gibt True bei Erfolg, False bei Fehler zurück.
    """
    if not (window and area and region and space):
        return False

    try:
        with bpy.context.temp_override(
            window=window, area=area, region=region, space_data=space
        ):
            bpy.ops.clip.track_markers(backwards=backwards, sequence=sequence)
        return True
    except Exception as e:
        return False
