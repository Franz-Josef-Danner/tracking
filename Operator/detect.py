import bpy
import math

class CLIP_OT_detect(bpy.types.Operator):
    bl_idname = "clip.detect"
    bl_label = "detect"
    bl_description = "Automatischer Suchzyklus für Markerplatzierung"

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        tracking = clip.tracking if clip else None
        settings = tracking.settings if tracking else None

        if not clip or not tracking or not settings:
            self.report({'ERROR'}, "Kein gültiger Movie Clip gefunden.")
            return {'CANCELLED'}

        # Basiswerte
        ha = clip.size[0]
        margin_base = ha / 100
        min_distance_base = ha / 50
        marker_adapt = getattr(scene, "marker_frame", 20) * 4
        max_marker = int(marker_adapt * 1.1)
        min_marker = int(marker_adapt * 0.9)
        detection_threshold = 0.5
        factor = math.log10(detection_threshold * 100000000) / 8
        margin = int(margin_base * factor)
        min_distance = int(min_distance_base * factor)

        attempt = 0
        while attempt < 20:
            factor = math.log10(detection_threshold * 100000000) / 8
            margin = int(margin_base * factor)
            min_distance = int(min_distance_base * factor)

            # Proxy deaktivieren
            clip.use_proxy = False

            # Feature Detection ausführen
            bpy.ops.clip.detect_features(
                margin=margin,
                min_distance=min_distance,
                threshold=detection_threshold
            )

            # Anzahl der neuen Marker zählen (aktive Auswahl)
            anzahl_neu = sum(1 for track in tracking.tracks if track.select)

            if anzahl_neu > min_marker:
                if anzahl_neu < max_marker:
                    self.report({'INFO'}, f"Ziel erreicht mit {anzahl_neu} Markern.")
                    return {'FINISHED'}
                else:
                    # Threshold anpassen
                    detection_threshold = max(min(detection_threshold * ((anzahl_neu + 0.1) / marker_adapt), 1.0), 0.0001)
                    bpy.ops.clip.delete_track()
            else:
                detection_threshold = max(detection_threshold * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)
                bpy.ops.clip.delete_track()

            attempt += 1

        self.report({'WARNING'}, "Maximale Versuche erreicht. Teilcyclus 1 abgebrochen.")
        return {'CANCELLED'}
