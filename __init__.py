bl_info = {
    "name": "Kaiserlich Tracking Optimizer",
    "author": "Franz (converted by ChatGPT)",
    "version": (1, 0, 0),
    "blender": (4, 4, 3),
    "location": "Movie Clip Editor > Sidebar > Kaiserlich",
    "description": (
        "Automatisches Motion-Tracking mit adaptiver Marker-"
        "Platzierung und Kamera-Lösung"
    ),
    "category": "Tracking",
}

import bpy
from bpy.props import StringProperty

from . import ui


def register():
    print("Registering Kaiserlich Tracking Optimizer")
    bpy.types.Scene.kaiserlich_marker_counts = StringProperty(
        name="Kaiserlich Marker Counts",
        description="JSON-kodierte Markerzählung für Debugging-Zwecke",
        default="",
    )
    ui.register()


def unregister():
    print("Unregistering Kaiserlich Tracking Optimizer")
    del bpy.types.Scene.kaiserlich_marker_counts
    ui.unregister()


if __name__ == "__main__":
    register()
