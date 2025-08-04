import math


def compute_marker_error_std(tracking):
    """Compute sum of marker position standard deviations."""
    std_sums = []
    for track in tracking.tracks:
        if len(track.markers) < 2:
            continue
        xs = [m.co[0] for m in track.markers if not m.mute]
        ys = [m.co[1] for m in track.markers if not m.mute]
        if len(xs) < 2:
            continue
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs) / len(xs))
        std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / len(ys))
        std_sums.append(std_x + std_y)
    return sum(std_sums)


__all__ = ["compute_marker_error_std"]
