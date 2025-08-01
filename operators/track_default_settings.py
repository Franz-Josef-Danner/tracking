"""Operator to set default Blender tracking settings."""

import bpy


class TRACKING_OT_set_default_settings(bpy.types.Operator):
    """Set default tracking settings"""
    bl_idname = "tracking.set_default_settings"
    bl_label = "Default Settings"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden")
            return {'CANCELLED'}

        settings = clip.tracking.settings

        # Auflösung des Movie Clips auslesen
        width = clip.size[0]

        # Neue Berechnungen für Pattern- und Suchgröße
        pattern_size = int(width / 100)
        search_size = pattern_size * 2

        settings.default_pattern_size = pattern_size
        settings.default_search_size = search_size
        settings.default_motion_model = 'Loc'
        settings.default_pattern_match = 'KEYFRAME'
        settings.use_default_brute = True
        settings.use_default_normalization = True
        settings.use_default_red_channel = True
        settings.use_default_green_channel = True
        settings.use_default_blue_channel = True
        settings.default_weight = 1.0
        settings.default_correlation_min = 0.9
        settings.default_margin = 10

        self.report({'INFO'}, f"Tracking-Defaults gesetzt (Pattern: {pattern_size}, Search: {search_size})")
        return {'FINISHED'}


classes = (TRACKING_OT_set_default_settings,)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
