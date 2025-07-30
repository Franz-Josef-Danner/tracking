import bpy
from bpy.props import BoolProperty
from ..helpers import set_tracking_channels

class CLIP_OT_setup_defaults(bpy.types.Operator):
    bl_idname = "clip.setup_defaults"
    bl_label = "Test Defaults"
    bl_description = (
        "Setzt Tracking-Standards: Pattern 10, Motion Loc, Keyframe-Match"
    )

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        settings.default_pattern_size = 10
        settings.default_search_size = settings.default_pattern_size * 2
        settings.default_motion_model = 'Loc'
        settings.default_pattern_match = 'KEYFRAME'
        settings.use_default_brute = True
        settings.use_default_normalization = True
        set_tracking_channels(clip, True, True, True)

        settings.default_weight = 1.0
        settings.default_correlation_min = 0.9
        settings.default_margin = 10
        if hasattr(settings, 'use_default_mask'):
            settings.use_default_mask = False

        if not self.silent:
            self.report({'INFO'}, "Tracking-Defaults gesetzt")
        return {'FINISHED'}


operator_classes = (
    CLIP_OT_setup_defaults,
)
