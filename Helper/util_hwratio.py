import bpy
from typing import Optional
from .util_clip import get_active_clip

def get_hw_ratio(context: Optional[bpy.types.Context]) -> float:
    try:
        clip = get_active_clip(context)
        if clip:
            w, h = clip.size
            if isinstance(w, (int, float)) and isinstance(h, (int, float)) and h > 0:
                return float(w) / float(h)
    except Exception:
        pass
    try:
        scene = (context.scene if context else bpy.context.scene)
        rx = float(getattr(scene.render, "resolution_x", 0))
        ry = float(getattr(scene.render, "resolution_y", 0))
        if ry > 0:
            return rx / ry
    except Exception:
        pass
    return 1.0