import bpy

class CLIP_OT_api_defaults(bpy.types.Operator):
    bl_idname = "clip.api_defaults"
    bl_label = "Defaults"
    bl_description = (
        "Setzt Standardwerte f\u00fcr Pattern, Suche, Motion Model und mehr"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        settings.default_pattern_size = 50
        settings.default_search_size = 100
        settings.default_motion_model = 'Loc'
        settings.default_pattern_match = 'KEYFRAME'
        settings.use_default_brute = True
        settings.use_default_normalization = True
        settings.use_default_red_channel = True
        settings.use_default_green_channel = True
        settings.use_default_blue_channel = True
        settings.default_weight = 1.0
        settings.default_correlation_min = 0.9
        settings.default_margin = 100

        self.report({'INFO'}, "Tracking-Defaults gesetzt")
        return {'FINISHED'}


operator_classes = (
    CLIP_OT_api_defaults,
)
