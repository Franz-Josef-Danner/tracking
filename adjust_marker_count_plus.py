"""Utility: modify scene marker count plus."""


def adjust_marker_count_plus(scene, delta):
    """Update marker count plus while clamping to the base value."""

    base_plus = scene.min_marker_count * 4
    new_val = max(base_plus, scene.min_marker_count_plus + delta)
    new_val = min(new_val, scene.min_marker_count * 200)
    scene.min_marker_count_plus = new_val

