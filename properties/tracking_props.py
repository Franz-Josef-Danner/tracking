import bpy
from bpy.props import IntProperty, FloatProperty

tracking_properties = {
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
    "threshold_value": FloatProperty(
        name="Threshold Value",
        description="Gespeicherter Threshold-Wert",
        default=1.0,
    ),
    "tracker_threshold": FloatProperty(
        name="Tracker Threshold",
        description="Zuletzt verwendeter Threshold-Wert",
        default=0.5,
    ),
    "error_threshold": FloatProperty(
        name="Error Threshold",
        description="Fehlergrenze für Operationen",
        default=2.0,
    ),
}

def register_props():
    for name, prop in tracking_properties.items():
        setattr(bpy.types.Scene, name, prop)

def unregister_props():
    for name in tracking_properties.keys():
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
