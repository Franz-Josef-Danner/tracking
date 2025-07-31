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
    """Führt den Marker-Platzierungs-Zyklus als modalen Operator aus."""

    bl_idname = "tracking.place_marker"
    bl_label = "Place Marker"
    bl_description = (
        "Führt Marker-Platzierungs-Zyklus aus (Teil-Zyklus 1, max. 20 Versuche inkl. Proxy-Deaktivierung)"
    )

    _timer = None

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        self.clip = getattr(context.space_data, "clip", None)
        if self.clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        self.tracking = self.clip.tracking
        settings = self.tracking.settings

        self.detection_threshold = getattr(settings, "default_correlation_min", 0.75)
        self.marker_adapt = scene.get("marker_adapt", 80)
        self.max_marker = scene.get("max_marker", self.marker_adapt * 1.1)
        self.min_marker = scene.get("min_marker", self.marker_adapt * 0.9)

        image_width = self.clip.size[0]
        self.margin_base = int(image_width * 0.025)
        self.min_distance_base = int(image_width * 0.05)

        self.attempt = 0
        self.success = False
        self.state = "DETECT"

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene

        if self.state == "DETECT":
            for t in self.tracking.tracks:
                t.select = False

            self.frame = scene.frame_current
            self.width, self.height = self.clip.size
            self.distance_px = int(self.width * 0.04)

            self.existing_positions = []
            for track in self.tracking.tracks:
                marker = track.markers.find_frame(self.frame, exact=True)
                if marker and not marker.mute:
                    self.existing_positions.append((marker.co[0] * self.width, marker.co[1] * self.height))

            perform_marker_detection(
                self.clip,
                self.tracking,
                self.detection_threshold,
                self.margin_base,
                self.min_distance_base,
            )

            self.initial_track_names = {t.name for t in self.tracking.tracks}
            self.wait_start = time.time()
            self.state = "WAIT"
            self.report({'INFO'}, f"Versuch {self.attempt + 1}: Marker gesetzt, warte...")
            return {'PASS_THROUGH'}

        if self.state == "WAIT":
            current_names = {t.name for t in self.tracking.tracks}
            if current_names != self.initial_track_names or time.time() - self.wait_start >= 3.0:
                self.state = "PROCESS"
            return {'PASS_THROUGH'}

        if self.state == "PROCESS":
            new_tracks = [t for t in self.tracking.tracks if t.select]
            close_tracks = []
            for track in new_tracks:
                marker = track.markers.find_frame(self.frame, exact=True)
                if marker and not marker.mute:
                    x = marker.co[0] * self.width
                    y = marker.co[1] * self.height
                    for ex, ey in self.existing_positions:
                        if math.hypot(x - ex, y - ey) < self.distance_px:
                            close_tracks.append(track)
                            break

            for t in self.tracking.tracks:
                t.select = False
            for t in close_tracks:
                t.select = True
            if close_tracks:
                bpy.ops.clip.delete_track()

            cleaned_tracks = [t for t in new_tracks if t not in close_tracks]
            for t in self.tracking.tracks:
                t.select = False
            for t in cleaned_tracks:
                t.select = True

            anzahl_neu = len(cleaned_tracks)

            meldung = f"Versuch {self.attempt + 1}:\nGesetzte Marker (nach Filterung): {anzahl_neu}"
            if anzahl_neu < self.min_marker:
                meldung += "\nMarkeranzahl zu niedrig.\nMarker werden gelöscht."
            elif anzahl_neu > self.max_marker:
                meldung += "\nMarkeranzahl ausreichend. Vorgang wird beendet."
            else:
                meldung += "\nMarkeranzahl im mittleren Bereich.\nErneuter Versuch folgt."
            bpy.ops.clip.marker_status_popup('INVOKE_DEFAULT', message=meldung)

            if self.min_marker <= anzahl_neu <= self.max_marker:
                self.report({'INFO'}, f"Markeranzahl im Zielbereich: {anzahl_neu}")
                self.success = True
                context.window_manager.event_timer_remove(self._timer)
                return {'FINISHED'}
            else:
                if anzahl_neu < self.min_marker:
                    for t in self.tracking.tracks:
                        t.select = False
                    for t in cleaned_tracks:
                        t.select = True
                    bpy.ops.clip.delete_track()

                self.detection_threshold = max(
                    self.detection_threshold * ((anzahl_neu + 0.1) / self.marker_adapt),
                    0.0001,
                )

                print(
                    f"\U0001f4cc Versuch {self.attempt + 1}: Marker={anzahl_neu}, "
                    f"Threshold={self.detection_threshold:.4f}"
                )

                self.attempt += 1
                if self.attempt >= 20:
                    self.report({'WARNING'}, "Maximale Versuche erreicht, Markeranzahl unzureichend.")
                    context.window_manager.event_timer_remove(self._timer)
                    return {'FINISHED'}

                self.state = "DETECT"
                return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)



# Registrierung
def register():
    bpy.utils.register_class(TRACKING_OT_place_marker)


def unregister():
    bpy.utils.unregister_class(TRACKING_OT_place_marker)


if __name__ == "__main__":
    register()
