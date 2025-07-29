bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 200),
    "blender": (4, 4, 0),
    "location": "View3D > Object",
    "description": "Zeigt eine einfache Meldung an",
    "category": "Object",
}

try:
    import bpy  # type: ignore
except ModuleNotFoundError:  # allow import outside Blender
    bpy = None

# Use relative imports within the add-on package
import os
if bpy is not None and not os.environ.get("BLENDER_TEST"):
    from .operators import operator_classes
    from .ui import panel_classes
    from .properties import register_properties, unregister_properties
    classes = operator_classes + panel_classes


def register():
    if bpy is None:
        return
    register_properties()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            print(f"\u26a0\ufe0f  Class already registered: {cls.__name__}")


def unregister():
    if bpy is None:
        return
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            print(f"\u26a0\ufe0f  Could not unregister: {cls.__name__}")
    unregister_properties()


if __name__ == "__main__":
    register()

