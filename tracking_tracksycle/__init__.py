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
from .modules.ui.kaiserlich_panel import KAISERLICH_PT_tracking_tools
from bpy.props import IntProperty, FloatProperty, BoolProperty

classes = [
    KAISERLICH_OT_auto_track_cycle,
    KAISERLICH_PT_tracking_tools,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.min_marker_count = IntProperty(
        name="Minimale Markeranzahl",
        description="Anzahl an erkannten Features, die mindestens erreicht werden soll",
        default=10,
        min=1,
    )

    bpy.types.Scene.min_track_length = IntProperty(
        name="Tracking-L\u00e4nge (min)",
        description="Minimale Anzahl Frames pro Marker",
        default=10,
        min=1,
    )

    bpy.types.Scene.error_threshold = FloatProperty(
        name="Fehler-Schwelle",
        description="Maximal tolerierter Reprojektionfehler",
        default=5.0,
        min=0.0,
    )

    bpy.types.Scene.debug_output = BoolProperty(
        name="\U0001F527 Debug Output aktivieren",
        description="Aktiviert ausführliches Logging zur Fehleranalyse",
        default=False,
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.min_track_length
    del bpy.types.Scene.error_threshold
    del bpy.types.Scene.debug_output


if __name__ == "__main__":
    register()

