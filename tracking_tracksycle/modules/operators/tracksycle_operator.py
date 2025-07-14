"""Core operator for the Kaiserlich Tracksycle addon."""

import bpy

from ..proxy.proxy_wait import create_proxy_and_wait, remove_existing_proxies
from ..detection.distance_remove import distance_remove
from ..detection.find_frame_with_few_tracking_markers import (
    find_frame_with_few_tracking_markers,
)
from ..tracking.track import track_markers
from ..tracking.Track_Length import get_track_length
from ..tracking.motion_model import next_model
from ..playback.set_playhead import set_playhead
from ..util.tracker_logger import TrackerLogger


class KAISERLICH_OT_auto_track_cycle(bpy.types.Operator):
    """Start the automated tracking cycle"""

    bl_idname = "kaiserlich.auto_track_cycle"
    bl_label = "Auto Track Cycle"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        space = context.space_data
        clip = getattr(space, "clip", None)
        if not clip:
            self.report({'ERROR'}, "No clip loaded")
            return {'CANCELLED'}

        logger = TrackerLogger(debug=scene.debug_output)

        # state machine property
        scene.kaiserlich_tracking_state = 'WAIT_FOR_PROXY'

        remove_existing_proxies(clip)
        logger.info("Generating proxy...")
        if not create_proxy_and_wait(clip):
            self.report({'ERROR'}, "Proxy creation timed out")
            return {'CANCELLED'}

        scene.kaiserlich_tracking_state = 'DETECTING'

        settings = clip.tracking.settings
        threshold = 1.0
        expected = scene.min_marker_count * 4
        pattern_size = getattr(settings, "default_pattern_size", 11)

        for _ in range(10):
            clip.proxy.build_50 = False
            clip.use_proxy = False
            bpy.ops.clip.detect_features(threshold=threshold,
                                        margin=clip.size[0]/200,
                                        distance=clip.size[0]/20)
            marker_count = len(clip.tracking.tracks)
            if marker_count >= scene.min_marker_count:
                break
            threshold = max(round(threshold * ((marker_count + 0.1) / expected), 5), 0.0001)
            if pattern_size < 100:
                pattern_size = min(int(pattern_size * 1.1), 100)
                settings.default_pattern_size = pattern_size

        scene.kaiserlich_tracking_state = 'TRACKING'

        # Filter markers near GOOD_ markers
        margin = clip.size[0] / 20
        for track in list(clip.tracking.tracks):
            if track.name.startswith("GOOD_"):
                distance_remove(clip.tracking.tracks, track.markers[0].co, margin)

        for track in clip.tracking.tracks:
            if not track.name.startswith("TRACK_"):
                track.name = f"TRACK_{track.name}"

        track_markers(context)

        scene.kaiserlich_tracking_state = 'CLEANUP'

        for track in list(clip.tracking.tracks):
            if get_track_length(track) < scene.min_track_length:
                clip.tracking.tracks.remove(track)

        sparse_frame = find_frame_with_few_tracking_markers(clip, scene.min_marker_count)
        if sparse_frame is not None:
            next_model(settings)
            if pattern_size < 100:
                pattern_size = min(int(pattern_size * 1.1), 100)
                settings.default_pattern_size = pattern_size
            set_playhead(sparse_frame)

        scene.kaiserlich_tracking_state = 'REVIEW'
        logger.info("Tracking cycle finished")
        return {'FINISHED'}


