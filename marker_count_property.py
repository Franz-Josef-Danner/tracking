import bpy


def count_new_markers(context):
    """Return number of tracks starting with ``NEU_`` on the active clip."""
    clip = context.space_data.clip
    if not clip:
        return 0
    return sum(1 for t in clip.tracking.tracks if t.name.startswith("NEU_"))


class CLIP_OT_marker_count_property(bpy.types.Operator):
    """Update ``scene.new_marker_count`` with current NEU_ marker count."""

    bl_idname = "clip.marker_count_property"
    bl_label = "Count New Markers"

    def execute(self, context):
        context.scene.new_marker_count = count_new_markers(context)
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_marker_count_property)
    bpy.types.Scene.new_marker_count = bpy.props.IntProperty(
        name="New Marker Count",
        default=0,
    )


def unregister():
    del bpy.types.Scene.new_marker_count
    bpy.utils.unregister_class(CLIP_OT_marker_count_property)


if __name__ == "__main__":
    register()
