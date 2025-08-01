"""Operator to set default tracking settings for the active movie clip."""

import bpy


class CLIP_OT_track_default_settings(bpy.types.Operator):
    """Set default pattern and search size for tracking"""

    bl_idname = "clip.track_default_settings"
    bl_label = "Set Default Tracking Settings"
    bl_description = "Set default pattern and search size for movie clip tracking"

    @classmethod
    def poll(cls, context):
        return (
            context.space_data is not None
            and context.space_data.type == 'CLIP_EDITOR'
            and context.edit_movieclip is not None
        )

    def execute(self, context):
        clip = context.edit_movieclip
        settings = clip.tracking.settings

        # Beispielhafte feste Werte – können später dynamisiert werden
        settings.default_pattern_size = 12
        settings.default_search_size = 24

        self.report({'INFO'}, "Default tracking settings applied")
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
