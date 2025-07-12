"""Calculate and store marker count thresholds."""


def compute_marker_count_plus(base):
    """Return marker count values derived from ``base``.

    The main value is ``marker_count_plus`` which is four times ``base``. Two
    additional values represent 80% and 120% of this number and are returned as
    a tuple ``(marker_count_plus, count_min, count_max)``.
    """

    marker_count_plus = int(base * 4)
    return (
        marker_count_plus,
        int(marker_count_plus * 0.8),
        int(marker_count_plus * 1.2),
    )


def update_marker_count_plus(scene):
    """Compute marker count limits from ``min_marker_count``.

    The main value ``min_marker_count_plus`` is four times the user input.
    Two additional properties ``marker_count_plus_min`` and
    ``marker_count_plus_max`` are 80%% and 120%% of that value.
    The computed count is returned for convenience.
    """

    base = getattr(scene, "min_marker_count", 0)
    marker_count_plus, count_min, count_max = compute_marker_count_plus(base)
    scene.min_marker_count_plus = marker_count_plus
    scene.marker_count_plus_min = count_min
    scene.marker_count_plus_max = count_max
    scene.new_marker_count = marker_count_plus
    return marker_count_plus
