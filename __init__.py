bl_info = {
    "name": "Tracking Tools",
    "author": "Addon Author",
    "version": (1, 97, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor",
    "description": "Beispiel Addon mit Marker Basis Value",
    "category": "Tracking",
}

try:
    import bpy  # type: ignore
except ModuleNotFoundError:
    bpy = None

import os
if bpy is not None and not os.environ.get("BLENDER_TEST"):
    from .operators import operator_classes
    from .ui.panels import panel_classes
    from .properties import register_properties, unregister_properties
    from .helpers.cycle_motion_model import TRACKING_OT_cycle_motion_model

    classes = operator_classes + (TRACKING_OT_cycle_motion_model,) + panel_classes
else:
    classes = ()


def register():
    if bpy is None:
        return
    register_properties()
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass


def unregister():
    if bpy is None:
        return
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except ValueError:
            pass
    unregister_properties()


if __name__ == "__main__":
    register()
