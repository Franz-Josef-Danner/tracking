"""Core operator for the Kaiserlich Tracksycle addon."""

import bpy

from ..proxy.proxy_wait import (
    create_proxy_and_wait_async,
    remove_existing_proxies,
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

        ctx = context.copy()
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                ctx['area'] = area
                break
        bpy.ops.clip.rebuild_proxy('INVOKE_DEFAULT')

        # state machine property
        scene.kaiserlich_tracking_state = 'WAIT_FOR_PROXY'

        def nach_proxy():
            def delayed_call():
                # Optional: Sicherstellen, dass der richtige Frame gesetzt ist
                bpy.context.scene.frame_set(bpy.context.scene.frame_current)

                # Jetzt Feature Detection sicher aufrufen
                bpy.ops.clip.detect_features(
                    threshold=1.0,
                    margin=26,
                    min_distance=265,
                )
                return None  # nur einmal ausführen

            # Verzögerung von 0.5 Sekunden
            bpy.app.timers.register(delayed_call, first_interval=0.5)

        remove_existing_proxies(clip, logger=logger)
        logger.info("Generating proxy...")
        if not create_proxy_and_wait_async(clip, callback=nach_proxy, logger=logger):
            self.report({'ERROR'}, "Proxy creation timed out")
            return {'CANCELLED'}

        return {'FINISHED'}


