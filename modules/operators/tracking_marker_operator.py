"""Operator implementing custom tracking workflow."""

from __future__ import annotations

import bpy

from ..detection.detect_no_proxy import detect_features_no_proxy
from ..detection.distance_remove import distance_remove
from ..util.tracking_utils import hard_remove_new_tracks
from ..util.tracker_logger import TrackerLogger, configure_logger


class KAISERLICH_OT_tracking_marker(bpy.types.Operator):  # type: ignore[misc]
    """Detect features with iterative threshold adjustment."""

    bl_idname = "kaiserlich.tracking_marker"
    bl_label = "Tracking Marker"
    bl_options = {'REGISTER', 'UNDO'}

    attempts: bpy.props.IntProperty(name="Versuche", default=10, min=1)

    def execute(self, context):  # type: ignore[override]
        space = context.space_data
        clip = getattr(space, "clip", None)
        if not clip:
            self.report({'ERROR'}, "No clip loaded")
            return {'CANCELLED'}

        scene = context.scene
        configure_logger(debug=getattr(scene, "debug_output", False))
        logger = TrackerLogger()

        width, height = clip.size
        logger.info(f"Auflösung: {width} x {height}")

        margin = width * 0.01
        dist_px = width * 0.002

        threshold = 1.0
        expected = getattr(scene, "min_marker_count", 10) * 4

        for _ in range(self.attempts):
            space.detection_margin = margin
            space.detection_distance = int(dist_px)
            space.detection_threshold = threshold

            detect_features_no_proxy(
                clip,
                threshold=threshold,
                margin=margin,
                min_distance=dist_px,
                logger=logger,
            )

            existing_names = {t.name for t in clip.tracking.tracks}
            idx = 0
            for track in clip.tracking.tracks:
                if track.name.startswith(("Track", "Track.", "Track_")):
                    new_name = f"NEW_{idx:03}"
                    while new_name in existing_names:
                        idx += 1
                        new_name = f"NEW_{idx:03}"
                    track.name = new_name
                    track.pattern_size = 50
                    track.search_size = 100
                    existing_names.add(new_name)
                    idx += 1

            good_tracks = [t for t in clip.tracking.tracks if t.name.startswith("GOOD_")]
            frame = scene.frame_current
            for good in good_tracks:
                marker = None
                if hasattr(good.markers, "find_frame"):
                    mi = good.markers.find_frame(frame)
                    if mi != -1:
                        marker = good.markers[mi]
                if marker is None:
                    marker = next(
                        (m for m in good.markers if getattr(m, "frame", None) == frame),
                        None,
                    )
                if marker:
                    distance_remove(clip.tracking.tracks, marker.co, dist_px, logger=logger)

            nm = len([t for t in clip.tracking.tracks if t.name.startswith("NEW_")])
            min_valid = expected * 0.8
            max_valid = expected * 1.2
            if min_valid <= nm <= max_valid:
                for track in clip.tracking.tracks:
                    if track.name.startswith("NEW_"):
                        track.name = track.name.replace("NEW_", "TRACK_")
                logger.info("Detection erfolgreich")
                return {'FINISHED'}

            threshold = max(round(threshold * ((nm + 0.1) / expected), 5), 0.0001)
            hard_remove_new_tracks(clip, logger=logger)

        for track in clip.tracking.tracks:
            if track.name.startswith("NEW_"):
                track.name = track.name.replace("NEW_", "TRACK_")
        return {'FINISHED'}


__all__ = ["KAISERLICH_OT_tracking_marker"]
