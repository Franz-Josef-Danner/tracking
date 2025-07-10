"""Utility: retrieve or calculate marker count plus."""


def get_marker_count_plus(scene):
    """Return stored value or the default derived from the base count."""
    return scene.get("_marker_count_plus", scene.min_marker_count * 4)
