import math

from .utils import MIN_THRESHOLD


def marker_target_aggressive(marker_frame):
    """Return an aggressive target based on marker_frame."""
    return int(marker_frame * 4)


def marker_target_conservative(marker_frame):
    """Return a conservative target based on marker_frame."""
    return int(marker_frame * 2)


def calculate_base_values(clip):
    """Return margin and min distance base values derived from clip width."""
    width, _ = clip.size
    margin_base = int(width * 0.025)
    min_distance_base = int(width * 0.05)
    return margin_base, min_distance_base


def apply_threshold_to_margin_and_distance(threshold, margin_base, min_distance_base):
    """Return scaled margin and min distance based on threshold."""
    if margin_base == 0 or min_distance_base == 0:
        raise ValueError(
            "Ungültige Basiswerte für margin/min_distance – wurde die Clipgröße korrekt gesetzt?"
        )
    detection_threshold = max(min(threshold, 1.0), MIN_THRESHOLD)
    factor = math.log10(detection_threshold * 100000000) / 8
    margin = int(margin_base * factor)
    min_distance = int(min_distance_base * factor)
    return margin, min_distance, detection_threshold
