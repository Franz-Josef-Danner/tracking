import bpy
import math
import time

# Globaler Kontext für Markerprüfung
_global_marker_context = {}

def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    threshold: float,
    margin_base: int,
    min_distance_base: int,
) -> int:
    factor = math.log10(threshold * 1e8) / 8
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    if clip.use_proxy:
        clip.use_proxy = False

    result = bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=threshold,
    )

    if result != {"FINISHED"}:
        print(f"[Warnung] Feature Detection nicht erfolgreich: {result}")

    selected_tracks = [t for t in tracking.tracks if t.select]
    return len(selected_tracks)


def marker_wait_callback():
    tracking = _global_marker_context["tracking"]
    current_names = {t.name for t in tracking.tracks}
    initial_names = _global_marker_context["initial_track_names"]
    start_time = _global_marker_context["start_time"]

    if current_names != initial_names:
        print("📌 Neue Marker erkannt – fortsetzen.")
        bpy.ops.tracking.place_marker_continue()
        return None

    if time.time() - start_time > 3.0:
        print("⏱ Timeout (3s) – fortsetzen auch ohne neue Marker.")
        bpy.ops.tracking.place_marker_continue()
        return None

    return 0.25  # In 0.25 Sekunden erneut prüfen


class TRACKING_OT_place_marker_start(bpy.types.Operator):
    bl_idname = "tracking.place_marker_start"
    bl_label = "Marker setzen – Schritt 1"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        tracking = clip.tracking
        settings = tracking.settings

        detection_threshold = getattr(settings, "default_correlation_min", 0.75)
        image_width = clip.size[0]
        margin_base = int(image_width * 0.025)
        min_distance_base = int(image_width * 0.05)

        for t in tracking.tracks:
            t.select = False

        perform_marker_detection(
            clip,
            tracking,
            detection_threshold,
            margin_base,
            min_distance_base,
        )

        _global_marker_context["clip"] = clip
        _global_marker_context["tracking"] = tracking
        _global_marker_context["frame"] = scene.frame_current
        _global_marker_context["marker_adapt"] = scene.get("marker_adapt", 80)
        _global_marker_context["initial_track_names"] = {t.name for t in tracking.tracks}
        _global_marker_context["start_time"] = time.time()

        bpy.app.timers.register(marker_wait_callback, first_interval=0.25)

        self.report({'INFO'}, "Marker gesetzt. Warten auf Benutzeraktion oder Timeout...")
        return {'FINISHED'}


class TRACKING_OT_place_marker_continue(bpy.types.Operator):
    bl_idname = "tracking.place_marker_continue"
    bl_label = "Marker setzen – Schritt 2"

    def execute(self, context):
        if not _global_marker_context:
            self.report({'ERROR'}, "Kontextdaten fehlen.")
            return {'CANCELLED'}

        clip = _global_marker_context["clip"]
        tracking = _global_marker_context["tracking"]
        frame = _global_marker_context["frame"]
        marker_adapt = _global_marker_context["marker_adapt"]
        width, height = clip.size
        distance_px = int(width * 0.04)

        max_marker = marker_adapt * 1.1
        min_marker = marker_adapt * 0.9

        existing_positions = []
        for track in tracking.tracks:
            marker = track.markers.find_frame(frame, exact=True)
            if marker and not marker.mute:
                existing_positions.append((marker.co[0] * width, marker.co[1] * height))

        new_tracks = [t for t in tracking.tracks if t.select]
        close_tracks = []

        for track in new_tracks:
            marker = track.markers.find_frame(frame, exact=True)
            if marker and not marker.mute:
                x = marker.co[0] * width
                y = marker.co[1] * height
                for ex, ey in existing_positions:
                    if math.hypot(x - ex, y - ey) < distance_px:
                        close_tracks.append(track)
                        break

        for t in tracking.tracks:
            t.select = False
        for t in close_tracks:
            t.select = True
        if close_tracks:
            bpy.ops.clip.delete_track()

        cleaned_tracks = [t for t in new_tracks if t not in close_tracks]
        for t in tracking.tracks:
            t.select = False
        for t in cleaned_tracks:
            t.select = True

        anzahl_neu = len(cleaned_tracks)

        meldung = f"Auswertung abgeschlossen:\nGültige Marker: {anzahl_neu}"
        bpy.ops.clip.marker_status_popup('INVOKE_DEFAULT', message=meldung)

        self.report({'INFO'}, f"{anzahl_neu} Marker nach Prüfung beibehalten.")
        return {'FINISHED'}


# Registrierung
def register():
    bpy.utils.register_class(TRACKING_OT_place_marker_start)
    bpy.utils.register_class(TRACKING_OT_place_marker_continue)


def unregister():
    bpy.utils.unregister_class(TRACKING_OT_place_marker_start)
    bpy.utils.unregister_class(TRACKING_OT_place_marker_continue)


if __name__ == "__main__":
    register()