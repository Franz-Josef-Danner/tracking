import bpy
import logging

logger = logging.getLogger(__name__)


def auto_track_bidirectional(context):
    """Track selected markers backward then forward from the current frame."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        logger.info("Kein Clip gefunden")
        return

    # Proxy vor dem Tracking aktivieren
    if not clip.use_proxy:
        bpy.ops.clip.toggle_proxy()

    scene = context.scene
    current_frame = scene.frame_current
    logger.info("Starte Rueckwaerts-Tracking")
    bpy.ops.clip.track_markers(backwards=True, sequence=True)
    logger.info("Rueckwaerts-Tracking abgeschlossen")
    scene.frame_current = current_frame
    logger.info("Starte Vorwaerts-Tracking")
    bpy.ops.clip.track_markers(backwards=False, sequence=True)
    logger.info("Vorwaerts-Tracking abgeschlossen")
    scene.frame_current = current_frame
