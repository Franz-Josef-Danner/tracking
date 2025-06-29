bl_info = {
    "name": "Auto Track Menu",
    "blender": (2, 80, 0),
    "category": "Clip",
    "author": "Auto Generated",
    "version": (1, 0, 0),
    "description": "Add auto track entries to the Clip menu",
}

import bpy


class CLIP_OT_auto_track_settings(bpy.types.Operator):
    """Show the auto track sidebar in the Clip Editor"""

    bl_idname = "clip.auto_track_settings"
    bl_label = "Auto Track Settings"

    def execute(self, context):
        area = context.area
        if area.type == 'CLIP_EDITOR':
            area.spaces.active.show_region_ui = True
            self.report({'INFO'}, "Auto Track settings opened")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Clip Editor not active")
            return {'CANCELLED'}


class CLIP_OT_auto_track_start(bpy.types.Operator):
    """Run Blender's auto tracking on the active clip"""

    bl_idname = "clip.auto_track_start"
    bl_label = "Auto Track Start"

    def execute(self, context):
        try:
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


def draw_auto_track_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator(CLIP_OT_auto_track_settings.bl_idname, text="Auto Track Settings")
    layout.operator(CLIP_OT_auto_track_start.bl_idname, text="AUTO TRACK START")


classes = (
    CLIP_OT_auto_track_settings,
    CLIP_OT_auto_track_start,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.CLIP_MT_clip.append(draw_auto_track_menu)


def unregister():
    bpy.types.CLIP_MT_clip.remove(draw_auto_track_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
