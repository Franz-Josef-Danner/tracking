"""Adjust the ``min_marker_count_plus`` property when too few markers are found.

The helper lowers the expectation gradually so detection thresholds can be
reduced in the next iteration.  ``new_marker_count`` is the number of markers
found in the previous run.
"""


def adjust_marker_count_plus(scene, new_marker_count):
    """Decrease the expected marker count based on the last result."""

    current = scene.min_marker_count_plus
    if new_marker_count >= current:
        return current

    reduced = int(current * 0.9)
    scene.min_marker_count_plus = max(1, max(reduced, new_marker_count))
    return scene.min_marker_count_plus
