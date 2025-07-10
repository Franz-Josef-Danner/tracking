"""Utility: store marker count plus within allowed bounds."""


def set_marker_count_plus(scene, value):
    """Clamp and store marker count plus based on the base marker count."""
    base = scene.min_marker_count
    value = max(base * 4, min(value, base * 200))
    scene["_marker_count_plus"] = int(value)
    scene.min_marker_count_plus_min = int(value * 0.8)
    scene.min_marker_count_plus_max = int(value * 1.2)

