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
from .properties import TRACKING_PG_detect_settings

modules = [
    operators,
    ui,
]

def reload_modules():
    for m in modules:
        importlib.reload(m)

import bpy

from .operators.detect_markers import TRACKING_OT_detect_markers
from .ui.panel import TRACKING_PT_tools_panel

classes = (
    TRACKING_PG_detect_settings,
    TRACKING_OT_detect_markers,
    TRACKING_PT_tools_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.tracking_detect_settings = bpy.props.PointerProperty(type=TRACKING_PG_detect_settings)


def unregister():
    if hasattr(bpy.types.Scene, 'tracking_detect_settings'):
        del bpy.types.Scene.tracking_detect_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
