def compute_error_value(tracking_obj):
    """Berechnet die durchschnittliche Standardabweichung der Marker-Positionen."""
    print("Computing error value for tracking object")
    total_std = 0.0
    count = 0
    for t in tracking_obj.tracks:
        positions = [m.co for m in t.markers if not m.mute]
        if len(positions) < 2:
            continue
        mean_x = sum(p[0] for p in positions) / len(positions)
        mean_y = sum(p[1] for p in positions) / len(positions)
        variance = sum(
            (p[0] - mean_x) ** 2 + (p[1] - mean_y) ** 2 for p in positions
        ) / len(positions)
        total_std += variance ** 0.5
        count += 1
    return total_std / count if count else None


__all__ = ["compute_error_value"]
