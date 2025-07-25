bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 168),
    "blender": (4, 4, 0),
    "location": "View3D > Object",
    "description": "Zeigt eine einfache Meldung an",
    "category": "Object",
}

import bpy
from bpy.props import IntProperty, FloatProperty

from .functions import core as functions
from .ui import panels

classes = functions.operator_classes + panels.panel_classes


def register():
    bpy.types.Scene.marker_frame = IntProperty(
        name="Marker/Frame",
        description="Frame für neuen Marker",
        default=20,
    )
    bpy.types.Scene.frames_track = IntProperty(
        name="Frames/Track",
        description="Anzahl der Frames pro Tracking-Schritt",
        default=25,
    )
    bpy.types.Scene.nm_count = IntProperty(
        name="NM",
        description="Anzahl der TEST_-Tracks nach Count",
        default=0,
    )
    bpy.types.Scene.threshold_value = FloatProperty(
        name="Threshold Value",
        description="Gespeicherter Threshold-Wert",
        default=1.0,
    )
    bpy.types.Scene.error_threshold = FloatProperty(
        name="Error Threshold",
        description="Fehlergrenze für Operationen",
        default=2.0,
    )
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, "marker_frame"):
        del bpy.types.Scene.marker_frame
    if hasattr(bpy.types.Scene, "frames_track"):
        del bpy.types.Scene.frames_track
    if hasattr(bpy.types.Scene, "nm_count"):
        del bpy.types.Scene.nm_count
    if hasattr(bpy.types.Scene, "threshold_value"):
        del bpy.types.Scene.threshold_value
    if hasattr(bpy.types.Scene, "error_threshold"):
        del bpy.types.Scene.error_threshold


if __name__ == "__main__":
    register()
