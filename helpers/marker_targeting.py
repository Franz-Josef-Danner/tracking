"""Utilities for computing detection targets and scaling values."""

def calculate_base_values(image_width: int):
    """Calculate base margin and min_distance from image width."""
    margin_base = int(image_width * 0.025)
    min_distance_base = int(image_width * 0.05)
    return margin_base, min_distance_base


def apply_threshold_to_margin_and_distance(threshold: float, margin_base: int, min_distance_base: int):
    """Scale margin and distance according to the current threshold."""
    margin = max(1, int(margin_base * threshold))
    min_distance = max(1, int(min_distance_base * threshold))
    return margin, min_distance


def marker_target_aggressive(marker_frame: int) -> int:
    """Return the desired marker count for aggressive detection."""
    return int(marker_frame * 4)


def marker_target_conservative(marker_frame: int) -> int:
    """Return the desired marker count for conservative detection."""
    return max(1, int(marker_frame / 3))
