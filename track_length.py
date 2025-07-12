import bpy
import logging

logger = logging.getLogger(__name__)

def delete_short_tracks_with_prefix(context, prefix="TRACK_", min_frames=25):
    """Delete tracks whose names start with ``prefix`` that are shorter than
    ``min_frames`` frames."""
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None)
    if clip is None:
        clip = getattr(context.scene, "clip", None)
    if not clip:
        logger.warning("Kein Clip gefunden")
        return 0

    active_obj = clip.tracking.objects.active
    tracks = active_obj.tracks
    to_delete = [t for t in tracks if t.name.startswith(prefix) and len(t.markers) < min_frames]
    for t in tracks:
        t.select = t in to_delete

    if not to_delete:
        logger.info("Keine zu kurzen Tracks gefunden")
        return 0

    if not context.area or context.area.type != 'CLIP_EDITOR':
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        for space in area.spaces:
                            if space.type == 'CLIP_EDITOR':
                                with context.temp_override(area=area, region=region, space_data=space):
                                    bpy.ops.clip.delete_track()
                                logger.info("%d Track(s) geloescht", len(to_delete))
                                return len(to_delete)
        logger.warning("Kein Clip Editor Bereich gefunden")
        return 0

    bpy.ops.clip.delete_track()
    logger.info("%d Track(s) geloescht", len(to_delete))
    return len(to_delete)
