import math
from .utils import MIN_THRESHOLD


def compute_threshold_factor(threshold: float) -> float:
    """Return logarithmic factor for margin and distance."""
    value = max(threshold, MIN_THRESHOLD)
    return math.log10(value * 100000000) / 8


def adjust_threshold(threshold: float, anzahl_neu: int, marker_adapt: float) -> float:
    """Adapt threshold based on new marker count."""
    if marker_adapt <= 0:
        return max(min(threshold, 1.0), MIN_THRESHOLD)
    new_value = threshold * ((anzahl_neu + 0.1) / marker_adapt)
    return max(min(new_value, 1.0), MIN_THRESHOLD)
