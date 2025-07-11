"""Keep derived marker properties in sync."""


def update_min_marker_props(scene, _context):
    """Update derived marker count properties when the base count changes."""
    base = scene.min_marker_count
    marker_count_plus = min(base * 4, base * 200)
    scene.min_marker_count_plus = marker_count_plus
    scene.marker_count_plus_min = marker_count_plus * 0.8
    scene.marker_count_plus_max = marker_count_plus * 1.2
