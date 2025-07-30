import bpy

class TRACKING_OT_set_default_settings(bpy.types.Operator):
    bl_idname = "tracking.set_default_settings"
    bl_label = "Default Settings"
    bl_description = "Setzt alle Standardwerte f\u00fcr das Tracking"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        tracking = clip.tracking
        settings = tracking.settings

        image_width = clip.size[0]
        margin = int(image_width * 0.025)
        min_distance = int(image_width * 0.05)
        detection_threshold = 0.5

        marker_basis = scene.get("marker_basis", 20)
        min_track_length = scene.get("frames_track", 10)

        pattern_size = int(image_width / 100)
        search_size = pattern_size

        settings.motion_model = 'Loc'
        settings.use_keyframe_selection = True
        settings.use_normalization = True

        settings.use_red_channel = True
        settings.use_green_channel = True
        settings.use_blue_channel = True

        settings.weight = 1.0
        settings.correlation_min = 0.9
        settings.use_mask = False

        if "repeat_frame" not in scene:
            scene["repeat_frame"] = {}

        self.report({'INFO'}, f"Defaults gesetzt: Margin={margin}, Pattern={pattern_size}")
        return {'FINISHED'}


operator_classes = (
    TRACKING_OT_set_default_settings,
)
