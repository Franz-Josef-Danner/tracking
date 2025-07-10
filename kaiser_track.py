bl_info = {
    "name": "Kaiser Track",
    "description": "Placeholder UI for a future unified tracking workflow",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

import bpy


class CLIP_OT_kaiser_start(bpy.types.Operator):
    """Start button placeholder"""

    bl_idname = "clip.kaiser_start"
    bl_label = "START"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        self.report({'INFO'}, "Kaiser Track not implemented yet")
        return {'FINISHED'}


class CLIP_PT_kaiser_panel(bpy.types.Panel):
    """UI panel for the Kaiser tracking tools"""

    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiser track'
    bl_label = "Kaiser track"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "kaiser_min_markers")
        layout.prop(scene, "kaiser_min_track_length")
        layout.prop(scene, "kaiser_error_threshold")
        layout.operator(CLIP_OT_kaiser_start.bl_idname, text="START", icon='REC')


classes = [
    CLIP_OT_kaiser_start,
    CLIP_PT_kaiser_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kaiser_min_markers = bpy.props.IntProperty(
        name="Min Marker Pro Frame",
        default=10,
        min=1,
    )
    bpy.types.Scene.kaiser_min_track_length = bpy.props.IntProperty(
        name="Min Tracking Length",
        default=25,
        min=1,
    )
    bpy.types.Scene.kaiser_error_threshold = bpy.props.IntProperty(
        name="Error Threshold",
        default=30,
        min=1,
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.kaiser_min_markers
    del bpy.types.Scene.kaiser_min_track_length
    del bpy.types.Scene.kaiser_error_threshold


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
