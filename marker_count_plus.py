"""Calculate and store marker count thresholds."""


def update_marker_count_plus(scene):
    """Compute marker count limits from ``kt_min_marker_per_frame``.

    The main value ``min_marker_count_plus`` is four times the user input.
    Two additional properties ``marker_count_plus_min`` and
    ``marker_count_plus_max`` are 80%% and 120%% of that value.
    The computed count is returned for convenience.
    """

    base = getattr(scene, "kt_min_marker_per_frame", 0)
    marker_count_plus = int(base * 4)
    scene.min_marker_count_plus = marker_count_plus
    scene.marker_count_plus_min = int(marker_count_plus * 0.8)
    scene.marker_count_plus_max = int(marker_count_plus * 1.2)
    return marker_count_plus
