bl_info = {
    "name": "Tracking Marker Tools",
    "author": "",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "Movie Clip Editor > Sidebar > Tracking",
    "description": "Operator zum automatischen Setzen von Markern (detect features) und Button im UI",
    "category": "Tracking",
}

import importlib
from . import operators, ui  # noqa: F401

modules = [
    operators,
    ui,
]

def reload_modules():
    for m in modules:
        importlib.reload(m)

import bpy
from bpy.props import IntProperty  # type: ignore

from .operators.detect_markers import TRACKING_OT_detect_markers
from .ui.panel import TRACKING_PT_tools_panel

classes = (
    TRACKING_OT_detect_markers,
    TRACKING_PT_tools_panel,
)

def register():
    # Scene Property fuer UI Eingabe
    bpy.types.Scene.marker_per_frame = IntProperty(
        name="Marker per Frame",
        description="Gewuenschte Anzahl von Markern pro Frame (derzeit nur Anzeige, noch ohne Logik)",
        default=50,
        min=0,
    )
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    # Property entfernen
    if hasattr(bpy.types.Scene, 'marker_per_frame'):
        delattr(bpy.types.Scene, 'marker_per_frame')

if __name__ == "__main__":
    register()
