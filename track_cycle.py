import bpy
import logging

from . import run_in_clip_editor

logger = logging.getLogger(__name__)


def auto_track_bidirectional(context):
    """Track selected markers backward then forward from the current frame.

    The tracking steps run via :func:`bpy.app.timers.register` so Blender's UI
    remains responsive during long tracking operations.
    """

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        logger.info("Kein Clip gefunden")
        return

    if not clip.use_proxy:
        bpy.ops.clip.toggle_proxy()

    scene = context.scene
    current_frame = scene.frame_current
    state = {"phase": "backward"}

    def step():
        if state["phase"] == "backward":
            logger.info("Starte Rueckwaerts-Tracking")

            def op():
                bpy.ops.clip.track_markers(backwards=True, sequence=True)

            run_in_clip_editor(clip, op)
            logger.info("Rueckwaerts-Tracking abgeschlossen")
            scene.frame_current = current_frame
            state["phase"] = "forward"
            return 0.1

        logger.info("Starte Vorwaerts-Tracking")

        def op():
            bpy.ops.clip.track_markers(backwards=False, sequence=True)

        run_in_clip_editor(clip, op)
        logger.info("Vorwaerts-Tracking abgeschlossen")
        scene.frame_current = current_frame
        return None

    bpy.app.timers.register(step)
