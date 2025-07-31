import bpy
import math


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
    bl_idname = "tracking.place_marker"
    bl_label = "Place Marker"
    bl_description = (
        "Führt Marker-Platzierungs-Zyklus aus (Teil-Zyklus 1, max. 20 Versuche inkl. Proxy-Deaktivierung)"
    )

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}
        tracking = clip.tracking
        settings = tracking.settings

        detection_threshold = getattr(settings, "default_correlation_min", 0.75)
        marker_adapt = scene.get("marker_adapt", 80)
        max_marker = scene.get("max_marker", marker_adapt * 1.1)
        min_marker = scene.get("min_marker", marker_adapt * 0.9)

        image_width = clip.size[0]
        margin_base = int(image_width * 0.025)
        min_distance_base = int(image_width * 0.05)

        success = False

        for attempt in range(20):
            perform_marker_detection(
                clip,
                tracking,
                detection_threshold,
                margin_base,
                min_distance_base,
            )

            names_before = {t.name for t in tracking.tracks}
            new_tracks = [t for t in tracking.tracks if t.select]

            frame = scene.frame_current
            width, height = clip.size
            distance_px = int(width * 0.04)

            valid_positions = []
            for track in tracking.tracks:
                if track not in new_tracks:
                    marker = track.markers.find_frame(frame, exact=True)
                    if marker and not marker.mute:
                        valid_positions.append((marker.co[0] * width, marker.co[1] * height))

            close_tracks = []
            for track in new_tracks:
                marker = track.markers.find_frame(frame, exact=True)
                if marker and not marker.mute:
                    x = marker.co[0] * width
                    y = marker.co[1] * height
                    for vx, vy in valid_positions:
                        if math.hypot(x - vx, y - vy) < distance_px:
                            close_tracks.append(track)
                            break

            for t in tracking.tracks:
                t.select = False
            for t in close_tracks:
                t.select = True
            if close_tracks:
                bpy.ops.clip.delete_track()

            cleaned_tracks = [t for t in new_tracks if t not in close_tracks]
            anzahl_neu = len(cleaned_tracks)

            meldung = f"Versuch {attempt + 1}:\nGesetzte Marker (nach Filterung): {anzahl_neu}"
            if anzahl_neu < min_marker:
                meldung += "\nMarkeranzahl zu niedrig.\nMarker werden gelöscht."
            elif anzahl_neu > max_marker:
                meldung += "\nMarkeranzahl ausreichend. Vorgang wird beendet."
            else:
                meldung += "\nMarkeranzahl im mittleren Bereich.\nErneuter Versuch folgt."

            bpy.ops.clip.marker_status_popup('INVOKE_DEFAULT', message=meldung)

            if min_marker <= anzahl_neu <= max_marker:
                self.report({'INFO'}, f"Markeranzahl im Zielbereich: {anzahl_neu}")
                success = True
                break
            else:
                detection_threshold = max(
                    detection_threshold * ((anzahl_neu + 0.1) / marker_adapt),
                    0.0001,
                )
                bpy.ops.clip.delete_track()

            print(
                f"📌 Versuch {attempt + 1}: Marker={anzahl_neu}, "
                f"Threshold={detection_threshold:.4f}"
            )

        if not success:
            self.report({'WARNING'}, "Maximale Versuche erreicht, Markeranzahl unzureichend.")

        return {'FINISHED'}
