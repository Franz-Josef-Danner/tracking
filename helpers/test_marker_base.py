import bpy


def test_marker_base(scene):
    """Return marker target value for the scene."""
    return getattr(scene, "marker_frame", 0)
