import bpy
from typing import Optional, List, Set

def get_active_clip(context: Optional[bpy.types.Context],
                    require_clip_editor: bool = False,
                    allow_global_fallback: bool = True) -> Optional[bpy.types.MovieClip]:
    # 1) Kontextbasiert
    clip = None
    if context:
        sd = getattr(context, "space_data", None)
        clip = getattr(sd, "clip", None) or getattr(context, "edit_movieclip", None)

    if clip:
        return clip

    # 2) Optional: Clip-Editor erzwingen
    if require_clip_editor:
        raise RuntimeError("Kein aktiver CLIP_EDITOR/Clip im Kontext.")

    # 3) Optionaler globaler Fallback
    if allow_global_fallback and bpy.data.movieclips:
        return bpy.data.movieclips[0]

    return None
