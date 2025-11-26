import bpy
from ..Helper.playhead_helper import get_start_frame, reset_to_frame

def call_get_start_frame(context=None):
    try:
        return get_start_frame(context) if context else get_start_frame()
    except TypeError:
        return get_start_frame()

def call_reset_to_frame(frame, context=None):
    try:
        return reset_to_frame(context, frame) if context else reset_to_frame(frame)
    except TypeError:
        return reset_to_frame(frame)

def set_scene_props(scene: bpy.types.Scene, **kwargs) -> None:
    """Best-effort Setter für Scene-Properties (float-cast, fail-soft)."""
    for k, v in kwargs.items():
        try:
            if hasattr(scene, k):
                setattr(scene, k, float(v))
        except Exception:
            pass