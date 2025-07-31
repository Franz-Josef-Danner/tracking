import bpy


def delete_selected_tracks() -> None:
    """Delete all selected tracks in the Clip Editor."""
    if bpy.ops.clip.delete_track.poll():
        bpy.ops.clip.delete_track()

