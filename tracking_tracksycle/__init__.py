bl_info = {
    "name": "Kaiserlich Tracksycle",
    "blender": (4, 0, 0),
    "category": "Clip",
}

import bpy
from .detect_features import KAISERLICH_OT_detect_features

classes = [KAISERLICH_OT_detect_features]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
