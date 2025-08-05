import bpy

class CLIP_OT_tracker_settings(bpy.types.Operator):
    bl_idname = "clip.tracker_settings"
    bl_label = "Tracker Settings anwenden"
    bl_description = "Setzt vordefinierte Tracking-Werte basierend auf Clip-Auflösung"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        width = clip.size[0]  # HA = horizontale Auflösung

        # Tracking Settings
        ts = clip.tracking.settings
        ts.default_motion_model = 'Loc'
        ts.default_pattern_match = 'KEYFRAME'
        ts.use_normalization = True
        ts.default_weight = 1.0
        ts.default_correlation_min = 0.9
        ts.default_margin = 100
        ts.use_default_mask = False
        ts.use_red_channel = True
        ts.use_green_channel = True
        ts.use_blue_channel = True
        ts.use_prepass = True
        ts.default_pattern_size = int(width / 100)
        ts.default_search_size = ts.default_pattern_size
        ts.clean_frames = context.scene.frames_track if hasattr(context.scene, "frames_track") else 20
        ts.clean_error = 0.5

        self.report({'INFO'}, "Tracking-Voreinstellungen gesetzt.")
        return {'FINISHED'}
