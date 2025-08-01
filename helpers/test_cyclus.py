def evaluate_tracking(context: bpy.types.Context):
    """Durchführen von Detection, Tracking und Fehlerbewertung."""
    # Marker platzieren und Tracking bis zum Ende durchführen
    try:
        bpy.ops.tracking.place_marker('EXEC_DEFAULT')
    except Exception as e:
        print(f"[Fehler] Marker-Platzierung fehlgeschlagen: {e}")
        return 0, float("inf"), 0

    track_markers_until_end()
    error = error_value(context)

    # Gesamtlänge aller Tracks ermitteln
    length_info = get_tracking_lengths()
    if isinstance(length_info, dict):
        length = sum(v["length"] for v in length_info.values())
    else:
        length = float(length_info) if length_info else 0.0

    # Score als Verhältnis von Länge zu Fehler
    score = length / error if error else 0
    return length, error, score

def find_optimal_pattern(context: bpy.types.Context):
    """Ermittelt die beste Pattern-Größe durch iteratives Vergrößern."""
    pattern = 1.0
    pattern_final = None
    bester_score = 0.0
    max_cycles = 100
    wiederholungen = 0
    max_wiederholungen = 4

    for _ in range(max_cycles):
        length, error, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            pattern_final = pattern
            wiederholungen = 0  # Verbesserung erzielt, Zähler zurücksetzen
        else:
            wiederholungen += 1
            if wiederholungen > max_wiederholungen:
                break  # Abbruch nach 4 erfolglosen Wiederholungen
        pattern *= 1.1  # Pattern-Größe für nächsten Zyklus um 10% erhöhen

    return pattern_final

def find_optimal_motion(context: bpy.types.Context):
    """Bestimmt das optimal passende Motion-Model durch iteratives Umschalten."""
    motion = 1.0
    motion_final = None
    bester_score = 0.0

    for _ in range(7):
        length, error, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            motion_final = motion
        cycle_motion_model()  # Zum nächsten Motion-Model wechseln
        # (Hier wird angenommen, dass cycle_motion_model() intern `motion` weiterstellt)

    return motion_final

def find_best_channel_combination(context: bpy.types.Context):
    """Findet die beste Kombination der Farbkanäle für das Tracking."""
    kombinationen = [
        ("R",),
        ("G",),
        ("B",),
        ("G", "R"),
        ("G", "B"),
        ("R", "G", "B"),
    ]
    bester_score = float("-inf")
    beste_kombination = None
    beste_length = 0.0
    bester_error = float("inf")

    for kombi in kombinationen:
        # Boolean-Werte für die einzelnen Farbkanäle bestimmen
        red = "R" in kombi
        green = "G" in kombi
        blue = "B" in kombi
        set_tracking_channels(red, green, blue)
        length, error, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            beste_kombination = kombi
            beste_length = length
            bester_error = error

    return beste_kombination, beste_length, bester_error

def run_tracking_optimization(context: bpy.types.Context):
    """Startet den kompletten Optimierungszyklus und gibt die besten Parameter zurück."""
    pattern_final = find_optimal_pattern(context)
    motion_final = find_optimal_motion(context)
    best_channels, best_length, best_error = find_best_channel_combination(context)
    search_size = pattern_final * 2 if pattern_final is not None else 0
    return {
        "pattern": pattern_final,
        "motion": motion_final,
        "channels": best_channels,
        "length": best_length,
        "error": best_error,
        "search_size": search_size,
    }
