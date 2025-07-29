def calculate_base_values(image_width):
    """Berechnet die Basiswerte fuer margin und min_distance anhand der Bildbreite."""
    margin_base = int(image_width * 0.025)
    min_distance_base = int(image_width * 0.05)
    return margin_base, min_distance_base


def apply_threshold_to_margin_and_distance(threshold, margin_base, min_distance_base):
    """Skaliert margin und min_distance entsprechend dem aktuellen Threshold-Wert."""
    margin = max(1, int(margin_base * threshold))
    min_distance = max(1, int(min_distance_base * threshold))
    return margin, min_distance


def marker_target_aggressive(marker_frame: int) -> int:
    """Return the desired marker count for aggressive detection."""
    return int(marker_frame * 4)


def marker_target_conservative(marker_frame: int) -> int:
    """Return the desired marker count for conservative detection."""
    return max(1, int(marker_frame / 3))
