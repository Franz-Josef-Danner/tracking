import bpy
from typing import Optional, List, Set

def get_active_clip(context: Optional[bpy.types.Context]) -> Optional[bpy.types.MovieClip]:
    try:
        if context and getattr(context, "space_data", None):
            clip = getattr(context.space_data, "clip", None)
            if clip:
                return clip
    except Exception:
        pass
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None

def list_track_names_from_clip(clip: Optional[bpy.types.MovieClip]) -> List[str]:
    if not clip:
        return []
    try:
        return [t.name for t in clip.tracking.tracks]
    except Exception:
        return []

def get_current_track_names(context: Optional[bpy.types.Context]) -> Set[str]:
    clip = get_active_clip(context)
    return set(list_track_names_from_clip(clip))