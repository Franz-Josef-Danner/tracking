import bpy
import math

from ..helpers.invoke_clip_operator_safely import invoke_clip_operator_safely
from ..helpers.proxy_disable import disable_proxy
from ..helpers.proxy_enable import enable_proxy


class CLIP_OT_kaiserlich_track(bpy.types.Operator):
    bl_idname = "clip.kaiserlich_track"
    bl_label = "Kaiserlich Track"
    bl_description = "Automatisches Tracking mit Kaiserlich Einstellungen"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and context.space_data.clip is not None
        )

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        tracking = clip.tracking
        settings = tracking.settings

        width = clip.size[0]
        margin_base = int(width * 0.025)
        min_distance_base = int(width * 0.05)
        detection_threshold = 0.5

        marker_basis = scene.marker_basis
        marker_plus = marker_basis * 4
        marker_adapt = marker_plus
        min_marker = int(marker_adapt * 0.9)
        max_marker = int(marker_adapt * 1.1)

        scene.marker_plus = marker_plus
        scene.marker_adapt = marker_adapt
        scene.min_marker = min_marker
        scene.max_marker = max_marker

        settings.default_motion_model = 'Loc'
        settings.default_pattern_match = 'KEYFRAME'
        settings.default_correlation_min = 0.9
        settings.use_default_red_channel = True
        settings.use_default_green_channel = True
        settings.use_default_blue_channel = True
        settings.default_pattern_size = int(width / 100)
        settings.default_search_size = int(width / 100)

        disable_proxy(clip)

        tracks = tracking.objects.active.tracks
        for track in tracks:
            track.select = False

        anzahl_neu = 0
        for _ in range(20):
            factor = math.log10(detection_threshold * 100000000) / 8
            margin = int(margin_base * factor)
            distance = int(min_distance_base * factor)

            invoke_clip_operator_safely(
                "detect_features",
                threshold=detection_threshold,
                margin=margin,
                min_distance=distance,
            )

            new_tracks = [t for t in tracks if t.select]
            anzahl_neu = len(new_tracks)
            if min_marker < anzahl_neu < max_marker:
                break

            detection_threshold = max(
                detection_threshold * ((anzahl_neu + 0.1) / marker_adapt),
                0.0001,
            )
            invoke_clip_operator_safely("delete_track")

        enable_proxy(clip)

        invoke_clip_operator_safely("track_markers", backwards=False, sequence=True)
        invoke_clip_operator_safely("track_markers", backwards=True, sequence=True)

        min_length = scene.frames_per_track
        for track in list(tracks):
            frames = [m.frame for m in track.markers if not m.mute]
            if not frames or (max(frames) - min(frames) + 1) < min_length:
                tracks.remove(track)

        bpy.ops.clip.cleanup_tracks()

        self.report({'INFO'}, f"{len(tracks)} Tracks nach Cleanup")
        return {'FINISHED'}
