import bpy
import math

class CLIP_OT_detect(bpy.types.Operator):
    bl_idname = "clip.detect"
    bl_label = "detect"
    bl_description = "Automatischer Suchzyklus für Markerplatzierung mit Distanzprüfung"

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        tracking = clip.tracking if clip else None
        settings = tracking.settings if tracking else None

        if not clip or not tracking or not settings:
            self.report({'ERROR'}, "Kein gültiger Movie Clip gefunden.")
            return {'CANCELLED'}

        width, height = clip.size
        frame_current = scene.frame_current

        # Bestehende Markerpositionen (Pixelkoordinaten)
        existing_positions = []
        for track in tracking.tracks:
            marker = track.markers.find_frame(frame_current, exact=True)
            if marker and not marker.mute:
                x = marker.co[0] * width
                y = marker.co[1] * height
                existing_positions.append((x, y))

        # Basiswerte
        ha = width
        margin_base = ha / 100
        min_distance_base = ha / 50
        marker_adapt = getattr(scene, "marker_frame", 20) * 4
        max_marker = int(marker_adapt * 1.1)
        min_marker = int(marker_adapt * 0.9)
        detection_threshold = 0.5

        attempt = 0
        while attempt < 20:
            factor = math.log10(detection_threshold * 100000000) / 8
            margin = int(margin_base * factor)
            min_distance = int(min_distance_base * factor)

            # Proxy deaktivieren
            clip.use_proxy = False

            # Feature Detection
            bpy.ops.clip.detect_features(
                margin=margin,
                min_distance=min_distance,
                threshold=detection_threshold
            )

            # Entferne zu nahe Marker (Distanzprüfung)
        if self.state == "PROCESS":
            new_tracks = [t for t in self.tracking.tracks if t.name not in self.initial_track_names]
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

            # Anzahl neuer Marker nach Filterung
            anzahl_neu = sum(1 for t in new_tracks if t not in close_tracks)

            if anzahl_neu > min_marker:
                if anzahl_neu < max_marker:
                    self.report({'INFO'}, f"Ziel erreicht mit {anzahl_neu} Markern.")
                    return {'FINISHED'}
                else:
                    detection_threshold = max(min(detection_threshold * ((anzahl_neu + 0.1) / marker_adapt), 1.0), 0.0001)
                    bpy.ops.clip.delete_track()
            else:
                detection_threshold = max(detection_threshold * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)
                bpy.ops.clip.delete_track()

            attempt += 1

        self.report({'WARNING'}, "Maximale Versuche erreicht. Teilzyklus abgebrochen.")
        return {'CANCELLED'}

def register():
    bpy.utils.register_class(CLIP_OT_detect)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_detect)

if __name__ == "__main__":
    register()
