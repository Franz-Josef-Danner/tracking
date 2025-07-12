"""Keep derived marker properties in sync.

When ``min_marker_count`` changes, the derived properties are
recalculated and ``scene.new_marker_count`` is set to the same value as
``scene.min_marker_count_plus`` so detection starts with the expected
count.
"""


def update_min_marker_props(scene, _context):
    """Update derived marker count properties when the base count changes."""
    base = scene.min_marker_count
    # Compute the target marker count as four times the base value
    marker_count_plus = base * 4
    scene.min_marker_count_plus = int(marker_count_plus)
    scene.marker_count_plus_min = int(marker_count_plus * 0.8)
    scene.marker_count_plus_max = int(marker_count_plus * 1.2)
    scene.new_marker_count = scene.min_marker_count_plus

