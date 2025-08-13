import bpy

class CLIP_OT_tracker_settings(bpy.types.Operator):
    bl_idname = "clip.tracker_settings"
    bl_label = "Tracker Settings anwenden"
    bl_description = "Setzt vordefinierte Tracking-Werte basierend auf Clip-Auflösung"

    def execute(self, context):
        # --- Preconditions ---
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        scene = context.scene
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
        ts.clean_frames = getattr(scene, "frames_track", 20)
        ts.clean_error  = getattr(scene, "error_track", 0.5)

        # --- Detection-Threshold initialisieren (Szenenvariable) ---
        # Business-Logik: Wenn bereits ein Wert aus einem früheren Detect-Lauf existiert, respektieren wir ihn.
        # Sonst initialisieren wir mit dem aktuellen Default des Trackers (Fallback 0.75).
        try:
            default_min = float(getattr(ts, "default_correlation_min", 0.75))
        except Exception:
            default_min = 0.75

        try:
            det_thr = float(scene.get("last_detection_threshold", default_min))
        except Exception:
            det_thr = default_min

        # Sanity Clamp
        if not (0.0 < det_thr <= 1.0):
            det_thr = max(min(det_thr, 1.0), 1e-4)

        scene["last_detection_threshold"] = float(det_thr)

        self.report({'INFO'}, "Tracking-Voreinstellungen gesetzt.")
        print(f"[TrackerSettings] Defaults angewendet. last_detection_threshold={scene['last_detection_threshold']:.6f}")
        print("[TrackerSettings] Übergabe an find_low_marker …")

        # --- Nächster Schritt in der Kette: Find Low Marker ---
        try:
            res = bpy.ops.clip.find_low_marker('INVOKE_DEFAULT', use_scene_basis=True)
            print(f"[TrackerSettings] Übergabe an find_low_marker → {res}")
        except Exception as e:
            self.report({'ERROR'}, f"find_low_marker konnte nicht gestartet werden: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


# Optional: Register/Unregister (falls nicht zentral gebündelt)
def register():
    try:
        bpy.utils.register_class(CLIP_OT_tracker_settings)
    except ValueError:
        pass

def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_tracker_settings)
    except ValueError:
        pass
