import bpy


def cleanup_error_tracks(scene, clip):
    """Wrapper around operator cleanup_error_tracks."""
    from ..operators.cleanup_tracks import cleanup_error_tracks as _cleanup
    _cleanup(scene, clip)


def cleanup_tracks():
    """Run the builtin cleanup operator if available."""
    if bpy.ops.clip.cleanup.poll():
        bpy.ops.clip.cleanup()


__all__ = ["cleanup_error_tracks", "cleanup_tracks"]
