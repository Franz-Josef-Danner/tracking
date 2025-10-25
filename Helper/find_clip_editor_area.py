import bpy
from typing import Tuple, Optional

def find_clip_editor_area(clip: Optional[bpy.types.MovieClip]) -> Tuple[Optional[bpy.types.Window], Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.SpaceClipEditor]]:
    """Finde eine CLIP_EDITOR Area für Context Override."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            for space in area.spaces:
                if space.type != "CLIP_EDITOR":
                    continue
                if getattr(space, "clip", None) == clip or space.clip is None:
                    region_window = next((r for r in area.regions if r.type == "WINDOW"), None)
                    if region_window:
                        return window, area, region_window, space
    return None, None, None, None