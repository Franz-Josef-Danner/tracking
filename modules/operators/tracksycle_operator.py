"""Core operator for the Kaiserlich Tracksycle addon."""

import bpy

from ..proxy.proxy_wait import (
    create_proxy_and_wait_async,
    remove_existing_proxies,
)
from ..detection.distance_remove import distance_remove
from ..detection.detect_no_proxy import detect_features_no_proxy
from ..detection.find_frame_with_few_tracking_markers import (
    find_frame_with_few_tracking_markers,
)
from ..tracking.track import track_markers
from ..tracking.track_length import get_track_length
from ..tracking.motion_model import next_model
from ..playback.set_playhead import set_playhead
from ..util.tracker_logger import TrackerLogger, configure_logger


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

        configure_logger(debug=scene.debug_output)
        logger = TrackerLogger()

        # Activate proxy settings before generating proxies
        clip.use_proxy = True
        clip.use_proxy_custom_directory = True
        clip.proxy.build_50 = True
        clip.proxy.build_25 = clip.proxy.build_75 = clip.proxy.build_100 = False
        clip.proxy.directory = "//proxy"
        clip.proxy.timecode = 'FREE_RUN_NO_GAPS'

        ctx = context.copy()
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                ctx['area'] = area
                break
        bpy.ops.clip.rebuild_proxy('INVOKE_DEFAULT')

        # state machine property
        scene.kaiserlich_tracking_state = 'WAIT_FOR_PROXY'

        def nach_proxy():
            scene.kaiserlich_tracking_state = 'DETECTING'

            settings = clip.tracking.settings
            threshold = 1.0
            expected = scene.min_marker_count * 4
            pattern_size = getattr(settings, "default_pattern_size", 11)

            for _ in range(10):
                detect_features_no_proxy(
                    clip,
                    threshold=threshold,
                    margin=clip.size[0] / 200,
                    min_distance=int(clip.size[0] / 20),
                    logger=logger,
                )
                marker_count = len(clip.tracking.tracks)
                if marker_count >= scene.min_marker_count:
                    break
                threshold = max(round(threshold * ((marker_count + 0.1) / expected), 5), 0.0001)
                logger.debug(f"Threshold adjusted to {threshold}")
                if pattern_size < 100:
                    pattern_size = min(int(pattern_size * 1.1), 100)
                    settings.default_pattern_size = pattern_size
                    logger.debug(f"Pattern size adjusted to {pattern_size}")

            scene.kaiserlich_tracking_state = 'TRACKING'

            # Filter markers near GOOD_ markers
            margin = clip.size[0] / 20
            for track in list(clip.tracking.tracks):
                if track.name.startswith("GOOD_"):
                    try:
                        marker_co = track.markers[0].co
                    except (IndexError, AttributeError):
                        logger.warn(
                            f"Track {track.name} has no markers; skipping distance check"
                        )
                        continue
                    distance_remove(clip.tracking.tracks, marker_co, margin)

            for track in clip.tracking.tracks:
                if not track.name.startswith("TRACK_"):
                    new_name = f"TRACK_{track.name}"
                    try:
                        track.name = new_name
                    except RuntimeError as exc:
                        logger.warn(
                            f"Failed to rename track {track.name} -> {new_name}: {exc}"
                        )

            if not track_markers(context, logger=logger):
                self.report(
                    {'ERROR'},
                    "Tracking markers failed; check console for details",
                )
                return

            scene.kaiserlich_tracking_state = 'CLEANUP'

            for track in list(clip.tracking.tracks):
                if get_track_length(track) < scene.min_track_length:
                    clip.tracking.tracks.remove(track)

            sparse_frame = find_frame_with_few_tracking_markers(
                clip, scene.min_marker_count
            )
            if sparse_frame is not None:
                next_model(settings)
                if pattern_size < 100:
                    pattern_size = min(int(pattern_size * 1.1), 100)
                    settings.default_pattern_size = pattern_size
                    logger.debug(f"Pattern size adjusted to {pattern_size}")
                set_playhead(sparse_frame)

            scene.kaiserlich_tracking_state = 'REVIEW'
            logger.info("Tracking cycle finished")

        remove_existing_proxies(clip, logger=logger)
        logger.info("Generating proxy...")
        if not create_proxy_and_wait_async(clip, callback=nach_proxy, logger=logger):
            self.report({'ERROR'}, "Proxy creation timed out")
            return {'CANCELLED'}

        return {'FINISHED'}


