"""Keep derived marker properties in sync.

When ``min_marker_count`` changes, the derived properties are
recalculated and ``scene.new_marker_count`` is set to the same value as
``scene.min_marker_count_plus`` so detection starts with the expected
count.
"""


from .marker_count_plus import compute_marker_count_plus


def update_min_marker_props(scene, _context):
    """Update derived marker count properties when the base count changes."""
    base = scene.min_marker_count
    marker_count_plus, count_min, count_max = compute_marker_count_plus(base)
    scene.min_marker_count_plus = marker_count_plus
    scene.marker_count_plus_min = count_min
    scene.marker_count_plus_max = count_max
    scene.marker_count_plus_base = marker_count_plus
    scene.new_marker_count = marker_count_plus

