import bpy


def track_markers_until_end(scene, backwards=False):
    """Track selected markers from the current frame until the scene end."""
    start = scene.frame_current
    end = scene.frame_end
    original_start = scene.frame_start
    original_end = scene.frame_end
    scene.frame_start = start
    scene.frame_end = end
    bpy.ops.clip.track_markers(backwards=backwards, sequence=True)
    scene.frame_start = original_start
    scene.frame_end = original_end
