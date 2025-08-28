import bpy

def std_dev(values):
    mean_val = sum(values) / len(values)
    return (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5

def error_value(scene):
    """Berechnet die Gesamt-Standardabweichung (X + Y) für selektierte Marker im aktiven Clip."""
    clip = bpy.context.space_data.clip
    if not clip:
        return None

    x_positions = []
    y_positions = []

    for track in clip.tracking.tracks:
        if not track.select:
            continue
        for marker in track.markers:
            if marker.mute:
                continue
            x_positions.append(marker.co[0])
            y_positions.append(marker.co[1])

    if not x_positions:
        return None

    error_x = std_dev(x_positions)
    error_y = std_dev(y_positions)
    total_error = error_x + error_y

    return total_error
