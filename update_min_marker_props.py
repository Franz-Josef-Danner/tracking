"""Keep derived marker properties in sync.

When ``min_marker_count`` changes, the derived properties are
recalculated and ``scene.new_marker_count`` is set to the same value as
``scene.min_marker_count_plus`` so detection starts with the expected
count.
"""


from marker_count_plus import update_marker_count_plus


def update_min_marker_props(scene, context):
    """Update derived marker properties when ``min_marker_count`` changes."""

    return update_marker_count_plus(scene, context)

