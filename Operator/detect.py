import bpy
import math
import time

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    factor = math.log10(threshold * 1e7) / 7
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=threshold,
    )

    # Interface unverändert belassen
    selected_tracks = [t for t in tracking.tracks if t.select]
    return len(selected_tracks)

def deselect_all_markers(tracking):
    for t in tracking.tracks:
        t.select = False

class CLIP_OT_detect(bpy.types.Operator):
    bl_idname = "clip.detect"
    bl_label = "Place Marker"
    bl_description = "Führt Marker-Platzierungs-Zyklus aus (Teil-Zyklus 1, max. 20 Versuche)"

    _timer = None

    @classmethod
    def poll(cls, context):
        return (
            context.area and
            context.area.type == "CLIP_EDITOR" and
            getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        scene["detect_status"] = "pending"

        if scene.get("tracking_pipeline_active", False):
            scene["detect_status"] = "failed"
            return {'CANCELLED'}

        self.clip = getattr(context.space_data, "clip", None)
        if self.clip is None:
            scene["detect_status"] = "failed"
            return {'CANCELLED'}

        self.tracking = self.clip.tracking
        settings = self.tracking.settings

        self.detection_threshold = scene.get(
            "last_detection_threshold",
            getattr(settings, "default_correlation_min", 0.75),
        )
        self.marker_adapt = scene.get("marker_adapt", 20)
        self.max_marker = scene.get("max_marker", (self.marker_adapt * 1.1) + 1)
        self.min_marker = scene.get("min_marker", (self.marker_adapt * 0.9) - 1)

        image_width = self.clip.size[0]
        self.margin_base = int(image_width * 0.025)
        self.min_distance_base = int(image_width * 0.05)

        self.attempt = 0
        self.state = "DETECT"

        deselect_all_markers(self.tracking)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene

        if self.state == "DETECT":
            if self.attempt == 0:
                deselect_all_markers(self.tracking)

            self.frame = scene.frame_current
            # Lookups cachen
            tracks = self.tracking.tracks
            self.width, self.height = self.clip.size
            w, h = self.width, self.height
            find_frame_exact = bpy.types.MovieTrackingMarkers.find_frame

            # existierende Marker-Posit
