def bootstrap(context):
    clip = context.edit_movieclip
    scene = context.scene

    # clip.size liefert (width, height)
    width, height = clip.size

    margin = width * 0.025          # Rand für Feature Detection
    min_distance = width * 0.025    # Mindestabstand für neue Marker (Pixel approx)
    pattern_size = width * 0.01     # Start Pattern Size (wird skaliert)
    search_size = pattern_size * 2  # Reserviert für zukünftige Erweiterung
    threshold = 1.0                 # Start Threshold (wird angepasst)

    expected_frame_markers = scene.kaiserlich_marker_per_frame
    target = (expected_frame_markers * 4) / 14   # Zielanzahl aus ursprünglicher Formel
    upper_goal = target * 1.1
    lower_goal = target * 0.9

    return {
        "width": width,
        "height": height,
        "ma": margin,
        "md": min_distance,
        "pz": pattern_size,
        "sz": search_size,
        "tr": threshold,
        "za": target,
        "og": upper_goal,
        "ug": lower_goal,
    }
