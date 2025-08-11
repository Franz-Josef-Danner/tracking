import bpy
import math
import time

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    factor = math.log10(threshold * 1e7) / 7
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    # Proxy-Handling entfernt

    result = bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=threshold,
    )
    if result != {"FINISHED"}:
        print(f"[Warnung] Feature Detection nicht erfolgreich: {result}")

    selected_tracks = [t for t in tracking.tracks if t.select]
    return len(selected_tracks)

def deselect_all_markers(tracking):
    for t in tracking.tracks:
        t.select = False

def delete_selected_tracks(tracking):
    tracks = tracking.tracks
    to_delete = [t for t in tracks if t.select]
    for t in to_delete:
        tracks.remove(t)

class CLIP_OT_detect(bpy.types.Operator):
    bl_idname = "clip.detect"
    bl_label = "Place Marker"
    bl_description = "Teil-Zyklus 1: Marker-Platzierung mit adaptivem Threshold (max. 20 Versuche)"

    _timer = None
    _attempt = 0
    _max_attempts = 20

    def _clamp(self, v, vmin=0.0001, vmax=1.0):
        return max(vmin, min(v, vmax))

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

        # Blockiere parallel laufende Tracking-Jobs
        if scene.get("tracking_pipeline_active", False):
            self.report({'WARNING'}, "Tracking-Vorgang aktiv – bitte warten.")
            scene["detect_status"] = "failed"
            return {'CANCELLED'}

        self.clip = getattr(context.space_data, "clip", None)
        if self.clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            scene["detect_status"] = "failed"
            return {'CANCELLED'}

        self.tracking = self.clip.tracking
        settings = self.tracking.settings

        # Basiswerte
        self.detection_threshold = scene.get(
            "last_detection_threshold",
            getattr(settings, "default_correlation_min", 0.75)
        )
        self.marker_adapt = int(scene.get("marker_adapt", 20))
        self.max_marker = int(scene.get("max_marker", (self.marker_adapt * 1.1) + 1))
        self.min_marker = int(scene.get("min_marker", (self.marker_adapt * 0.9) - 1))

        image_width = int(self.clip.size[0])
        self.margin_base = int(image_width * 0.025)
        self.min_distance_base = int(image_width * 0.05)

        self._attempt = 0

        print("[Info] Deselektiere alle Marker vor Start.")
        deselect_all_markers(self.tracking)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}  # <-- wichtig

    def modal(self, context, event):
        if event.type == 'ESC':
            self._finalize(context, status="failed", msg="Detect abgebrochen.")
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Haupt-Iteration pro Timer-Tick
        if self._attempt >= self._max_attempts:
            self._finalize(context, status="failed", msg="Detect: Max. Versuche erreicht.")
            return {'FINISHED'}

        self._attempt += 1

        # 1) Detect
        count = perform_marker_detection(
            self.clip, self.tracking,
            self.detection_threshold,
            self.margin_base, self.min_distance_base
        )
        print(f"[Detect] Versuch {self._attempt}: neu selektierte Marker = {count} | "
              f"Min={self.min_marker}, Max={self.max_marker}, Adapt={self.marker_adapt:.0f}, "
              f"Thr={self.detection_threshold:.5f}")

        # 2) Entscheidungslogik gemäß Vorgabe
        if count > self.min_marker:
            if count < self.max_marker:
                # Erfolg
                context.scene["last_detection_threshold"] = float(self.detection_threshold)
                self._finalize(context, status="success", msg="Detect erfolgreich.")
                return {'FINISHED'}
            else:
                # Zu viele Marker → Threshold adaptieren und neu
                self.detection_threshold = self._clamp(
                    self.detection_threshold * ((count + 0.1) / self.marker_adapt)
                )
                delete_selected_tracks(self.tracking)
                return {'RUNNING_MODAL'}
        else:
            # Zu wenige Marker → Threshold adaptieren und neu
            self.detection_threshold = self._clamp(
                self.detection_threshold * ((count + 0.1) / self.marker_adapt)
            )
            delete_selected_tracks(self.tracking)
            return {'RUNNING_MODAL'}

    def _finalize(self, context, *, status: str, msg: str):
        try:
            wm = context.window_manager
            if self._timer:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass
        context.scene["detect_status"] = status
        print(f"[Detect] {msg} (Status: {status})")
