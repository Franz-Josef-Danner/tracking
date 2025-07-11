"""Adjust the marker_count_plus property when too few markers are found."""


def adjust_marker_count_plus(scene, new_marker_count):
    """Lower ``min_marker_count_plus`` slightly based on detected markers."""
    current = scene.min_marker_count_plus
    # Reduce expectation by 10% to gradually ease requirements
    scene.min_marker_count_plus = max(1, int(current * 0.9))
    return scene.min_marker_count_plus
