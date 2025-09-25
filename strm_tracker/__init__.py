bl_info = {
    "name": "STRM Feature Tracker",
    "blender": (3, 6, 0),
    "category": "MovieClip",
    "version": (0, 1, 0),
    "author": "Dein Name",
    "description": "Analyse von STRM (Spatio-Temporal Region Map) für automatische Feature-Tracking-Seeds",
}

import bpy
from .strm_panel import STRM_PT_Panel
from .strm_ops import STRM_OT_Analyze


classes = (
    STRM_PT_Panel,
    STRM_OT_Analyze,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
