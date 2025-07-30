import bpy
import math


def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    threshold: float,
    margin_base: int,
    min_distance_base: int,
) -> int:
    """F\u00fchrt ``bpy.ops.clip.detect_features()`` aus und gibt die
    Anzahl der selektierten Marker zur\u00fcck."""

    import math

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
        "F\u00fchrt Marker-Platzierungs-Zyklus aus (Teil-Zyklus 1, max. 20 Versuche inkl. Proxy-Deaktivierung)"
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

        detection_threshold = getattr(
            settings, "default_correlation_min", 0.75
        )
        marker_adapt = scene.get("marker_adapt", 80)
        max_marker = scene.get("max_marker", marker_adapt * 1.1)
        min_marker = scene.get("min_marker", marker_adapt * 0.9)

        image_width = clip.size[0]
        margin_base = int(image_width * 0.025)
        min_distance_base = int(image_width * 0.05)

        success = False

        for attempt in range(20):
            anzahl_neu = perform_marker_detection(
                clip,
                tracking,
                detection_threshold,
                margin_base,
                min_distance_base,
            )

            meldung = f"Versuch {attempt + 1}:\nGesetzte Marker: {anzahl_neu}"
            if anzahl_neu < min_marker:
                meldung += "\nMarkeranzahl zu niedrig.\nMarker werden gel\u00f6scht."
            elif anzahl_neu > max_marker:
                meldung += "\nMarkeranzahl ausreichend. Vorgang wird beendet."
            else:
                meldung += "\nMarkeranzahl im mittleren Bereich.\nErneuter Versuch folgt."

            bpy.ops.clip.marker_status_popup('INVOKE_DEFAULT', message=meldung)

            new_threshold = detection_threshold

            if anzahl_neu > min_marker:
                if anzahl_neu > max_marker:
                    self.report({'INFO'}, f"Marker erfolgreich gesetzt: {anzahl_neu}")
                    success = True
                else:
                    new_threshold = max(
                        detection_threshold * ((anzahl_neu + 0.1) / marker_adapt),
                        0.0001,
                    )
                    bpy.ops.clip.delete_track()
            else:
                new_threshold = max(
                    detection_threshold * ((anzahl_neu + 0.1) / marker_adapt),
                    0.0001,
                )
                bpy.ops.clip.delete_track()

            print(
                f"\U0001F4CC Versuch {attempt + 1}: Marker={anzahl_neu}, "
                f"Threshold={new_threshold:.4f}"
            )

            detection_threshold = new_threshold

            if success:
                break

        if not success:
            self.report({'WARNING'}, "Maximale Versuche erreicht, Markeranzahl unzureichend.")
        return {'FINISHED'}
