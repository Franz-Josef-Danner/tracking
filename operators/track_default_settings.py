bl_info = {
    "name": "Tracking Tools",
    "author": "Addon Maintainer",
    "version": (1, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar > Addon",
    "description": "Minimal tracking addon with custom properties",
    "category": "Tracking",
}

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
        settings.default_pattern_size = 10
        settings.default_search_size = 20
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
        self.report({'INFO'}, "Tracking-Defaults gesetzt")
        return {'FINISHED'}


classes = (TRACKING_OT_set_default_settings,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
