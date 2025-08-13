import bpy

class CLIP_OT_tracker_settings(bpy.types.Operator):
    bl_idname = "clip.tracker_settings"
    bl_label = "Tracker Settings anwenden"
    bl_description = "Setzt vordefinierte Tracking-Werte basierend auf Clip-Auflösung"

    def execute(self, context):
        # --- Preconditions ---
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        width = int(clip.size[0])  # horizontale Auflösung

        # --- Tracking Settings ---
        ts = clip.tracking.settings
        ts.default_motion_model = 'Loc'
        ts.default_pattern_match = 'KEYFRAME'
        ts.use_default_normalization = True
        ts.default_weight = 1.0
        ts.default_correlation_min = 0.9
        ts.default_margin = 100
        ts.use_default_mask = False
        ts.use_default_red_channel = True
        ts.use_default_green_channel = True
        ts.use_default_blue_channel = True
        ts.use_default_brute = True
        ts.default_pattern_size = max(1, int(width / 100))
        ts.default_search_size = ts.default_pattern_size * 2
        ts.clean_frames = getattr(context.scene, "frames_track", 20)
        ts.clean_error  = getattr(context.scene, "error_track", 0.5)

        self.report({'INFO'}, "Tracking-Voreinstellungen gesetzt.")
        print("[TrackerSettings] Defaults angewendet. Übergabe an find_low_marker …")

        # --- Nächster Schritt in der Kette: Find Low Marker ---
        try:
            res = bpy.ops.clip.find_low_marker('INVOKE_DEFAULT', use_scene_basis=True)
            print(f"[TrackerSettings] Übergabe an find_low_marker → {res}")
        except Exception as e:
            self.report({'ERROR'}, f"find_low_marker konnte nicht gestartet werden: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}
