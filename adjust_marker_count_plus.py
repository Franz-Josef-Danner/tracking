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


def increase_marker_count_plus(scene, percent=0.1):
    """Increase ``scene.min_marker_count_plus`` by ``percent``."""

    current = scene.min_marker_count_plus
    increment = max(1, int(current * percent))
    new_value = current + increment
    scene.min_marker_count_plus = new_value
    scene.marker_count_plus_min = int(new_value * 0.8)
    scene.marker_count_plus_max = int(new_value * 1.2)
    scene.new_marker_count = new_value
    return new_value


def decrease_marker_count_plus(scene, base_value, percent=0.1):
    """Decrease ``scene.min_marker_count_plus`` but not below ``base_value``."""

    current = scene.min_marker_count_plus
    decrement = max(1, int(current * percent))
    new_value = max(base_value, current - decrement)
    scene.min_marker_count_plus = new_value
    scene.marker_count_plus_min = int(new_value * 0.8)
    scene.marker_count_plus_max = int(new_value * 1.2)
    scene.new_marker_count = new_value
    return new_value
