import bpy
import math
import time

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


class TRACKING_OT_place_marker(bpy.types.Operator):
    """Setzt Marker und prüft sie innerhalb eines modalen Operators."""

    bl_idname = "tracking.place_marker"
    bl_label = "Marker setzen"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        self.clip = context.space_data.clip
        self.tracking = self.clip.tracking
        settings = self.tracking.settings

        detection_threshold = getattr(settings, "default_correlation_min", 0.75)
        image_width = self.clip.size[0]
        margin_base = int(image_width * 0.025)
        min_distance_base = int(image_width * 0.05)

        for t in self.tracking.tracks:
            t.select = False

        perform_marker_detection(
            self.clip,
            self.tracking,
            detection_threshold,
            margin_base,
            min_distance_base,
        )

        self.frame = scene.frame_current
        self.marker_adapt = scene.get("marker_adapt", 80)
        self.initial_track_names = {t.name for t in self.tracking.tracks}
        self.start_time = time.time()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)

        self.report({'INFO'}, "Marker gesetzt. Warten auf Abschluss...")
        return {'RUNNING_MODAL'}


    def modal(self, context, event):
        if event.type == 'TIMER':
            current_names = {t.name for t in self.tracking.tracks}
            if current_names != self.initial_track_names or time.time() - self.start_time > 3.0:
                self.finish_processing(context)
                context.window_manager.event_timer_remove(self._timer)
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    def finish_processing(self, context):
        clip = self.clip
        tracking = self.tracking
        frame = self.frame
        marker_adapt = self.marker_adapt
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


# Registrierung
def register():
    bpy.utils.register_class(TRACKING_OT_place_marker)


def unregister():
    bpy.utils.unregister_class(TRACKING_OT_place_marker)


if __name__ == "__main__":
    register()
