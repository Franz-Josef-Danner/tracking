import bpy
from bpy.props import IntProperty

tracking_properties = {
    "marker_basis": IntProperty(
        name="Marker / Frame",
        description="Basiswert f\u00fcr Marker pro Frame",
        default=20,
        min=1,
    ),
}


def register_props():
    for name, prop in tracking_properties.items():
        setattr(bpy.types.Scene, name, prop)


def unregister_props():
    for name in tracking_properties.keys():
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
