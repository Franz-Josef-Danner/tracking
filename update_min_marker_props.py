"""Utility: keep derived marker properties in sync."""


def update_min_marker_props(scene, context):
    """Update derived marker count properties when the base count changes."""
    base = scene.min_marker_count
    scene.min_marker_count_plus = min(base * 4, base * 200)

