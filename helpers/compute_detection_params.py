import math
from .feature_math import apply_threshold_to_margin_and_distance
from .utils import MIN_THRESHOLD


def compute_detection_params(threshold_value, margin_base, min_distance_base):
    """Return detection threshold, margin and min distance."""
    if margin_base == 0 or min_distance_base == 0:
        raise ValueError(
            "Ungültige Basiswerte für margin/min_distance – wurde die Clipgröße korrekt gesetzt?"
        )
    detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)
    factor = math.log10(detection_threshold * 100000000) / 8
    margin, min_distance = apply_threshold_to_margin_and_distance(
        factor, margin_base, min_distance_base
    )
    return detection_threshold, margin, min_distance
