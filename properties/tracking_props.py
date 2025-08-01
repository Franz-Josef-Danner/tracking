import bpy
from bpy.props import IntProperty, FloatProperty

tracking_properties = {
    "marker_basis": IntProperty(
        name="Marker/Frame",
        description="Basiswert f\u00fcr Marker pro Frame",
        default=20,
        min=5,
    ),
    "frames_per_track": IntProperty(
        name="Frames/Track",
        description="Minimale L\u00e4nge eines g\u00fcltigen Tracks",
        default=25,
        min=5,
    ),
    "error_per_track": FloatProperty(
        name="Error/Track",
        description="Maximaler Fehler pro Track",
        default=0.5,
        min=0.1,
        max=1.0
    ),
    "marker_plus": IntProperty(
        name="Marker Plus",
        description="Interner Markerwert",
        default=0,
        min=0,
    ),
    "marker_adapt": IntProperty(
        name="Marker Adapt",
        description="Angepasste Markeranzahl",
        default=0,
        min=0,
    ),
    "max_marker": IntProperty(
        name="Max Marker",
        description="Obere Markergrenze",
        default=0,
        min=0,
    ),
    "min_marker": IntProperty(
        name="Min Marker",
        description="Untere Markergrenze",
        default=0,
        min=0,
    ),
}


def register_props():
    for name, prop in tracking_properties.items():
        setattr(bpy.types.Scene, name, prop)


def unregister_props():
    for name in tracking_properties.keys():
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
