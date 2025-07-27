import bpy
from bpy.props import IntProperty, FloatProperty

scene_properties = {
    "marker_frame": IntProperty(
        name="Marker/Frame",
        description="Frame für neuen Marker",
        default=20,
    ),
    "frames_track": IntProperty(
        name="Frames/Track",
        description="Anzahl der Frames pro Tracking-Schritt",
        default=25,
    ),
    "nm_count": IntProperty(
        name="NM",
        description="Anzahl der TEST_-Tracks nach Count",
        default=0,
    ),
    "threshold_value": FloatProperty(
        name="Threshold Value",
        description="Gespeicherter Threshold-Wert",
        default=1.0,
    ),
    "test_value": IntProperty(
        name="Test Value",
        description="Ergebniswert aus Testfunktionen",
        default=0,
    ),
    "error_threshold": FloatProperty(
        name="Error Threshold",
        description="Fehlergrenze für Operationen",
        default=2.0,
    ),
}

def register_properties():
    for name, prop in scene_properties.items():
        setattr(bpy.types.Scene, name, prop)

def unregister_properties():
    for name in scene_properties.keys():
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
