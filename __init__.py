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
    from .operators import track_default_settings
    from .operators.bidirectional_tracking_operator import (
        TRACKING_OT_bidirectional_tracking,
    )
    classes = operator_classes + panel_classes + (TRACKING_OT_bidirectional_tracking,)
else:
    classes = ()


def register():
    if bpy is None:
        return
    register_properties()
    track_default_settings.register()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    if bpy is None:
        return
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    track_default_settings.unregister()
    unregister_properties()


if __name__ == "__main__":
    register()
