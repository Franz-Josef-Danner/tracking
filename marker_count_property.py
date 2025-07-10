import bpy

"""Property registration for minimum marker count."""


def register():
    bpy.types.Scene.min_marker_count = bpy.props.IntProperty(
        name="Min Marker Count",
        default=5,
        min=5,
        max=50,
        description="Minimum markers to detect each run",
    )


def unregister():
    del bpy.types.Scene.min_marker_count
