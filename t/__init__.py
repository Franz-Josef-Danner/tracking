bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 196),
    "blender": (4, 4, 0),
    "location": "View3D > Object",
    "description": "Zeigt eine einfache Meldung an",
    "category": "Object",
}

import bpy

# Use absolute imports starting from the add-on package root
from t.operators import operator_classes
from t.ui import panel_classes
from t.properties import register_properties, unregister_properties
classes = operator_classes + panel_classes


def register():
    register_properties()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_properties()


if __name__ == "__main__":
    register()
