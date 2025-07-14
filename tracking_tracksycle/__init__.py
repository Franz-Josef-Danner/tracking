bl_info = {
    "name": "Kaiserlich Tracksycle",
    "description": "Automated tracking cycle for Blender with proxy handling and dynamic feature detection.",
    "author": "Kaiserlich",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "Clip Editor > Sidebar > Kaiserlich",
    "category": "Tracking",
}

import bpy

from .modules.operators.tracksycle_operator import KAISERLICH_OT_auto_track_cycle

classes = [
    KAISERLICH_OT_auto_track_cycle,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
