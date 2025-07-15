"""Core operator for the Kaiserlich Tracksycle addon."""

import bpy
import os

from ..util.tracker_logger import TrackerLogger, configure_logger
from ..detection.find_frame_with_few_tracking_markers import (
    find_frame_with_few_tracking_markers,
)
from ..detection.detect_no_proxy import detect_features_no_proxy


class KAISERLICH_OT_auto_track_cycle(bpy.types.Operator):
    """Start the automated tracking cycle"""

    bl_idname = "kaiserlich.auto_track_cycle"
    bl_label = "Auto Track Cycle"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _proxy_paths = []
    _clip = None
    _logger = None

    def run_detection_with_check(self, clip, scene, logger):
        """Asynchronous feature detection with marker count verification."""

        state = {"attempt": 0}

        def detect_step():
            logger.info(f"\u25B6 Feature Detection Durchlauf {state['attempt'] + 1}")
            state["attempt"] += 1

            ok = detect_features_no_proxy(
                clip,
                threshold=1.0,
                margin=clip.size[0] / 200,
                min_distance=265,
                logger=logger,
            )

            if not ok:
                logger.warning("\u274C Feature Detection fehlgeschlagen.")
                return None

            logger.info("\u2705 Marker gesetzt \u2013 pr\u00fcfe Anzahl...")
            min_count = getattr(scene, "min_marker_count", 10)
            frame = find_frame_with_few_tracking_markers(clip, min_count)

            if frame is not None:
                logger.warning(
                    f"\u26A0 Zu wenige Marker in Frame {frame}. L\u00f6sche Tracks und versuche erneut."
                )
                for track in list(clip.tracking.tracks):
                    safe_track = clip.tracking.tracks.get(track.name)
                    if safe_track:
                        clip.tracking.tracks.remove(safe_track)
                return 0.5

            logger.info("\U0001F389 Gen\u00fcgend Marker erkannt \u2013 fertig.")
            scene.kaiserlich_feature_detection_done = True
            return None

        bpy.app.timers.register(detect_step, first_interval=0.1)

    def execute(self, context):
        scene = context.scene
        scene.kaiserlich_feature_detection_done = False
        space = context.space_data
        clip = getattr(space, "clip", None)
        if not clip:
            self.report({'ERROR'}, "No clip loaded")
            return {'CANCELLED'}

        configure_logger(debug=scene.debug_output)
        logger = TrackerLogger()

        scene.proxy_built = False

        # Activate proxy settings before generating proxies
        clip.use_proxy = True
        clip.use_proxy_custom_directory = True
        clip.proxy.build_50 = True
        clip.proxy.build_25 = clip.proxy.build_75 = clip.proxy.build_100 = False
        clip.proxy.directory = "//proxy"
        clip.proxy.timecode = 'FREE_RUN_NO_GAPS'

        proxy_dir = bpy.path.abspath(clip.proxy.directory)
        os.makedirs(proxy_dir, exist_ok=True)
        alt_dir = os.path.join(proxy_dir, os.path.basename(clip.filepath))
        for d in (proxy_dir, alt_dir):
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.startswith("proxy_"):
                        try:
                            os.remove(os.path.join(d, f))
                        except OSError:
                            pass

        override = context.copy()
        override['area'] = next(
            a for a in context.screen.areas if a.type == 'CLIP_EDITOR'
        )
        override['region'] = next(
            r for r in override['area'].regions if r.type == 'WINDOW'
        )
        override['space_data'] = override['area'].spaces.active
        override['clip'] = clip

        with context.temp_override(**override):
            bpy.ops.clip.rebuild_proxy()

        scene.kaiserlich_tracking_state = 'WAIT_FOR_PROXY'

        proxy_file = "proxy_50.avi"
        direct_path = os.path.join(proxy_dir, proxy_file)
        alt_path = os.path.join(proxy_dir, os.path.basename(clip.filepath), proxy_file)

        self._clip = clip
        self._proxy_paths = [direct_path, alt_path]
        self._logger = logger
        self._checks = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        self.report({'INFO'}, "Proxy 50% Erstellung gestartet")
        logger.info("[Proxy] build started")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):  # type: ignore[override]
        if event.type == 'TIMER':
            if any(os.path.exists(p) for p in self._proxy_paths):
                context.window_manager.event_timer_remove(self._timer)
                if self._clip:
                    self._clip.use_proxy = False
                scene = context.scene
                scene.proxy_built = True
                self._logger.info("[Proxy] build finished")
                scene.kaiserlich_feature_detection_done = False
                self.run_detection_with_check(self._clip, scene, self._logger)

                def check_detection_done():
                    scene = bpy.context.scene
                    if not scene.kaiserlich_feature_detection_done:
                        return 0.5

                    self._logger.info("Detection abgeschlossen")
                    scene.kaiserlich_tracking_state = "DETECTING"
                    return None

                bpy.app.timers.register(check_detection_done)
                return {'RUNNING_MODAL'}
            self._checks += 1
        return {'PASS_THROUGH'}

    def cancel(self, context):  # type: ignore[override]
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        return {'CANCELLED'}


