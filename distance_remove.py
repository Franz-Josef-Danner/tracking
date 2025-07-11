"""Cleanup NEW_ markers that are too close to GOOD_ markers.

This script is intended for manual use in Blender's text editor. It registers
an operator that deletes NEW_ markers in the current frame when they are closer
than a configurable distance to existing GOOD_ markers.
"""

import bpy
from delet import delete_close_new_markers

bl_info = {
    "name": "NEW_ Marker Cleanup",
    "description": (
        "Entfernt NEW_-Marker, die im aktuellen Frame zu nah an GOOD_-Markern liegen"
    ),
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

class CLIP_OT_remove_close_new_markers(bpy.types.Operator):
    bl_idname = "clip.remove_close_new_markers"
    bl_label = "NEW_-Marker löschen (zu nahe an GOOD_)"
    bl_description = (
        "Löscht NEW_-Marker im aktuellen Frame, wenn sie zu nahe an GOOD_-Markern liegen"
    )

    bl_options = {"REGISTER", "UNDO"}

    min_distance: bpy.props.FloatProperty(
        name="Mindestabstand",
        default=0.02,
        description="Mindestabstand im normierten Raum (0-1) zum Löschen",
        min=0.0,
    )

    @classmethod
    def poll(cls, context):
        return (
            context.space_data
            and context.space_data.type == 'CLIP_EDITOR'
            and context.space_data.clip
        )

    def execute(self, context):
        success = delete_close_new_markers(
            context,
            self.min_distance,
            self.report,
        )
        return {'FINISHED'} if success else {'CANCELLED'}


class CLIP_PT_new_cleanup_tools(bpy.types.Panel):
    bl_label = "NEW_-Cleanup"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tools'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.window_manager, "cleanup_min_distance")
        op = layout.operator(CLIP_OT_remove_close_new_markers.bl_idname)
        op.min_distance = context.window_manager.cleanup_min_distance


def register():
    bpy.utils.register_class(CLIP_OT_remove_close_new_markers)
    bpy.utils.register_class(CLIP_PT_new_cleanup_tools)
    if not hasattr(bpy.types.WindowManager, "cleanup_min_distance"):
        bpy.types.WindowManager.cleanup_min_distance = bpy.props.FloatProperty(
            name="Mindestabstand",
            default=0.02,
            description="Mindestabstand im normierten Raum (0-1) zum Löschen",
            min=0.0,
        )


def unregister():
    if hasattr(bpy.types.WindowManager, "cleanup_min_distance"):
        del bpy.types.WindowManager.cleanup_min_distance
    bpy.utils.unregister_class(CLIP_OT_remove_close_new_markers)
    bpy.utils.unregister_class(CLIP_PT_new_cleanup_tools)


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
