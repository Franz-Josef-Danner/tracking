bl_info = {
    "name": "Test Tracking Addon",
    "author": "Addon Author",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor",
    "description": "Addon für Testfunktionen",
    "category": "Tracking",
}

import bpy
from .operators import operator_classes
from .ui.panels import panel_classes

classes = operator_classes + panel_classes


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
