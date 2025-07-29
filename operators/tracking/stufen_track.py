import bpy
from bpy.types import Operator

from ...helpers import (
    apply_threshold_to_margin_and_distance,
    marker_target_aggressive,
    enable_proxy,
    disable_proxy,
    detect_features_once,
    get_undertracked_markers,
    delete_selected_tracks,
    select_short_tracks,
    track_bidirectional,
    find_next_low_marker_frame,
    cleanup_all_tracks,
    cleanup_error_tracks,
    set_playhead_to_frame,
    optimize_tracking_parameters,
)
from ...helpers.threshold_math import compute_threshold_factor, adjust_threshold


class CLIP_OT_stufen_track(Operator):
    bl_idname = "clip.stufen_track"
    bl_label = "Track"
    bl_description = "F\u00fchrt den automatischen Tracking-Zyklus aus"

    def execute(self, context):
        clip = context.space_data.clip
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if bpy.ops.clip.proxy_build.poll():
            bpy.ops.clip.proxy_build()

        detection_threshold = 0.5
        marker_basis = context.scene.marker_frame
        min_track_length = context.scene.frames_track
        repeat_frame = {}

        pattern_size = 50
        search_size = 100

        tracking_settings = clip.tracking.settings
        tracking_settings.motion_model = 'Loc'
        tracking_settings.use_keyframe_selection = True
        tracking_settings.use_normalization = True
        tracking_settings.use_red_channel = True
        tracking_settings.use_green_channel = True
        tracking_settings.use_blue_channel = True
        tracking_settings.correlation_min = 0.9
        tracking_settings.use_mask = False

        scene = context.scene

        while True:
            marker_plus = marker_target_aggressive(marker_basis)
            marker_adapt = marker_plus
            max_marker = marker_adapt * 1.1
            min_marker = marker_adapt * 0.9

            for _ in range(20):
                factor = compute_threshold_factor(detection_threshold)
                margin, min_distance = apply_threshold_to_margin_and_distance(
                    factor, int(scene.render.resolution_x * 0.025), int(scene.render.resolution_x * 0.05)
                )
                disable_proxy()
                detect_features_once()
                anzahl_neu = len(get_undertracked_markers(clip, min_track_length))
                if anzahl_neu > min_marker:
                    if anzahl_neu > max_marker:
                        break
                    else:
                        detection_threshold = adjust_threshold(
                            detection_threshold, anzahl_neu, marker_adapt
                        )
                        delete_selected_tracks()
                else:
                    detection_threshold = adjust_threshold(
                        detection_threshold, anzahl_neu, marker_adapt
                    )
                    delete_selected_tracks()

            enable_proxy()
            track_bidirectional(scene.frame_start, scene.frame_end)
            select_short_tracks(min_track_length)
            delete_selected_tracks()

            frame, _ = find_next_low_marker_frame(scene, clip, scene.marker_frame)
            if frame is None:
                cleanup_error_tracks(scene, clip)
                cleanup_all_tracks(clip)
                frame, _ = find_next_low_marker_frame(scene, clip, scene.marker_frame)
                if frame is None:
                    break

            set_playhead_to_frame(scene, frame)

            if frame in repeat_frame:
                repeat_frame[frame] += 1
                if repeat_frame[frame] >= 10:
                    pattern_size = 10
                    search_size = 20
                    optimize_tracking_parameters()
                    search_size = min(pattern_size * 2, marker_adapt * 1.1, 100)
            else:
                repeat_frame[frame] = 1
                search_size = min(marker_adapt * 0.9, marker_plus)

        self.report({'INFO'}, "Tracking abgeschlossen")
        return {'FINISHED'}


operator_classes = (
    CLIP_OT_stufen_track,
)
