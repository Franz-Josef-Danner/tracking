import bpy
from bpy.props import IntProperty

test_properties = {
    "nm_count": IntProperty(
        name="NM",
        description="Anzahl der TEST_-Tracks nach Count",
        default=0,
    ),
    "test_value": IntProperty(
        name="Test Value",
        description="Ergebniswert aus Testfunktionen",
        default=0,
    ),
}

def register_props():
    for name, prop in test_properties.items():
        setattr(bpy.types.Scene, name, prop)

def unregister_props():
    for name in test_properties.keys():
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
