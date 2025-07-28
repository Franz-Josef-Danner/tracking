import bpy


def delete_selected_tracks():
    """Delete selected tracks if a clip is active."""
    clip = getattr(bpy.context.space_data, "clip", None)
    if clip is None:
        return False
    if bpy.ops.clip.delete_track.poll():
        bpy.ops.clip.delete_track()
        return True
    return False
