"""Operator to set default Blender tracking settings."""

import bpy


class CLIP_OT_track_default_settings(bpy.types.Operator):
    """Set default tracking settings"""
    bl_idname = "clip.track_default_settings"
    bl_label = "Set Default Tracking Settings"

    def execute(self, context):
        # Tracking-Defaultwerte setzen
        context.scene.tracking_settings.default_pattern_size = 12
        context.scene.tracking_settings.default_search_size = 24
        return {'FINISHED'}


classes = (CLIP_OT_track_default_settings,)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
