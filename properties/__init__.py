import bpy

class TrackingProperties(bpy.types.PropertyGroup):
    error_per_track: bpy.props.FloatProperty(
        name="Error/Track",
        description="Fehlergrenze pro Track für die Bereinigung",
        default=1.0 / 300.0,
        min=0.00001,
        max=1.0
    )

def register_props():
    bpy.utils.register_class(TrackingProperties)
    bpy.types.Scene.tracking_props = bpy.props.PointerProperty(
        name="Tracking Properties",
        type=TrackingProperties
    )

def unregister_props():
    if hasattr(bpy.types.Scene, "tracking_props"):
        del bpy.types.Scene.tracking_props
    bpy.utils.unregister_class(TrackingProperties)
