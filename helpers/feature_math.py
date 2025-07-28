def calculate_base_values(image_width):
    """Berechnet die Basiswerte für margin und min_distance anhand der Bildbreite."""
    margin_base = int(image_width * 0.025)
    min_distance_base = int(image_width * 0.05)
    return margin_base, min_distance_base


def apply_threshold_to_margin_and_distance(threshold, margin_base, min_distance_base):
    """Skaliert margin und min_distance entsprechend dem aktuellen Threshold-Wert."""
    margin = max(1, int(margin_base * threshold))
    min_distance = max(1, int(min_distance_base * threshold))
    return margin, min_distance
