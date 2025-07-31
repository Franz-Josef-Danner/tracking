bl_info = {
    "name": "Tracking Tools",
    "author": "Addon Author",
    "version": (1, 0, 0),
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
    classes = operator_classes + panel_classes
else:
    classes = ()


def register():
    if bpy is None:
        return
    register_properties()
    bpy.types.Scene.error_threshold = bpy.props.FloatProperty(
        name="Fehlertoleranz",
        description="Maximal erlaubter Trackingfehler",
        default=0.1,
        min=0.0,
    )
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    if bpy is None:
        return
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, "error_threshold"):
        del bpy.types.Scene.error_threshold
    unregister_properties()


if __name__ == "__main__":
    register()
