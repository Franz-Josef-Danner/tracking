import bpy
from .combined_cycle import adjust_marker_count_plus as _adjust


class CLIP_OT_adjust_marker_count_plus(bpy.types.Operator):
    """Adjust ``scene.min_marker_count_plus`` by ``delta``."""

    bl_idname = "clip.adjust_marker_count_plus"
    bl_label = "Adjust Marker Count Plus"

    delta: bpy.props.IntProperty(default=10)

    def execute(self, context):
        _adjust(context.scene, self.delta)
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_adjust_marker_count_plus)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_adjust_marker_count_plus)


if __name__ == "__main__":
    register()
