"""Core operator for the Kaiserlich Tracksycle addon."""

import bpy

from ..proxy.proxy_wait import (
    create_proxy_and_wait_async,
    remove_existing_proxies,
    detect_features_in_ui_context,
    _get_clip_editor_override,
)
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

        override = {"clip": clip}
        override.update(_get_clip_editor_override(context))
        bpy.ops.clip.rebuild_proxy(override)

        # state machine property
        scene.kaiserlich_tracking_state = 'WAIT_FOR_PROXY'

        def nach_proxy():
            def delayed_call():
                logger.debug("Executing detection callback")
                scene = bpy.context.scene
                space = bpy.context.space_data
                clip = getattr(space, "clip", None)
                if clip and clip.use_proxy:
                    clip.use_proxy = False
                    logger.debug("Proxy deaktiviert f\u00fcr Feature-Erkennung")

                # Optional: Sicherstellen, dass der richtige Frame gesetzt ist
                scene.frame_set(scene.frame_current)

                # Jetzt Feature Detection sicher aufrufen
                detect_features_in_ui_context(
                threshold=1.0,
                margin=26,
                min_distance=265,
                logger=logger,
                )
                return None  # nur einmal ausf\u00fchren

            # Verzögerung von 0.5 Sekunden
            logger.info("Proxy ready, scheduling feature detection")
            bpy.app.timers.register(delayed_call, first_interval=0.5)

        remove_existing_proxies(clip, logger=logger)
        logger.info("Generating proxy...")
        if not create_proxy_and_wait_async(clip, callback=nach_proxy, logger=logger):
            self.report({'ERROR'}, "Proxy creation timed out")
            return {'CANCELLED'}

        return {'FINISHED'}


