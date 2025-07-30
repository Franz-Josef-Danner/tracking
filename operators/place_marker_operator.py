import bpy
import math


class TRACKING_OT_place_marker(bpy.types.Operator):
    bl_idname = "tracking.place_marker"
    bl_label = "Place Marker"
    bl_description = (
        "F\u00fchrt Marker-Platzierungs-Zyklus aus (Teil-Zyklus 1, max. 20 Versuche inkl. Proxy-Deaktivierung)"
    )

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        tracking = clip.tracking
        settings = tracking.settings

        detection_threshold = settings.correlation_min
        marker_adapt = scene.get("marker_adapt", 80)
        max_marker = scene.get("max_marker", marker_adapt * 1.1)
        min_marker = scene.get("min_marker", marker_adapt * 0.9)

        image_width = clip.size[0]
        margin_base = int(image_width * 0.025)
        min_distance_base = int(image_width * 0.05)

        success = False

        for attempt in range(20):
            factor = math.log10(detection_threshold * 1e8) / 8
            margin = max(1, int(margin_base * factor))
            min_distance = max(1, int(min_distance_base * factor))

            # Proxy deaktivieren
            if clip.use_proxy:
                clip.use_proxy = False

            # Feature Detection
            bpy.ops.clip.detect_features(
                margin=margin,
                minimum_distance=min_distance,
                threshold=detection_threshold,
            )

            # Selektierte Marker z\u00e4hlen
            selected_tracks = [t for t in tracking.tracks if t.select]
            anzahl_neu = len(selected_tracks)

            if anzahl_neu > min_marker:
                if anzahl_neu > max_marker:
                    self.report({'INFO'}, f"Marker erfolgreich gesetzt: {anzahl_neu}")
                    success = True
                    break
                else:
                    detection_threshold = max(
                        detection_threshold * ((anzahl_neu + 0.1) / marker_adapt),
                        0.0001,
                    )
                    bpy.ops.clip.delete_track()
            else:
                detection_threshold = max(
                    detection_threshold * ((anzahl_neu + 0.1) / marker_adapt),
                    0.0001,
                )
                bpy.ops.clip.delete_track()

        if not success:
            self.report({'WARNING'}, "Maximale Versuche erreicht, Markeranzahl unzureichend.")
        return {'FINISHED'}
