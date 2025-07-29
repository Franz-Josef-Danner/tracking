import bpy


def delete_selected_tracks():
    """Delete selected tracks if a clip is active.

    This helper is called by various operators such as
    :class:`~operators.tracking.cleanup.CLIP_OT_track_cleanup` and
    :class:`~operators.tracking.detect.CLIP_OT_detect_button`.
    """
    clip = getattr(bpy.context.space_data, "clip", None)
    if clip is None:
        return False
    if bpy.ops.clip.delete_track.poll():
        bpy.ops.clip.delete_track()
        return True
    return False
