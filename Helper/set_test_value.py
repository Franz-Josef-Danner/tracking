def calculate_marker_values(scene):
    marker_basis = getattr(scene, "marker_frame", None)
    if marker_basis is None:
        return None

    marker_plus = marker_basis / 3
    marker_adapt = marker_plus
    max_marker = int(marker_adapt * 1.1)
    min_marker = int(marker_adapt * 0.9)
    marker_value = (marker_adapt + max_marker + min_marker) / 3

    scene["marker_adapt"] = marker_adapt
    scene["marker_max"] = max_marker
    scene["marker_min"] = min_marker
    scene["marker_value"] = marker_value

    return marker_value
