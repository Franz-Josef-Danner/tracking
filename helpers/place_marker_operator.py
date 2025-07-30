import bpy


def place_marker_operator(frame=None):
    """Add a marker on all selected tracks at the given frame."""
    if frame is not None:
        bpy.context.scene.frame_current = frame
    if bpy.ops.clip.add_marker_slide.poll():
        bpy.ops.clip.add_marker_slide()
