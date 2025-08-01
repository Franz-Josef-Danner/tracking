import bpy
import time
from .track_markers_until_end import track_markers_until_end
from .get_tracking_lengths import get_tracking_lengths

__all__ = [
    "evaluate_tracking",
    "find_optimal_pattern",
    "find_optimal_motion",
    "find_best_channel_combination",
    "run_tracking_optimization",
    "error_value"
]


def wait_for_marker_change(context, timeout: float = 0.5) -> bool:
    """
    Warte bis sich die Markeranzahl verändert oder ein Timeout erreicht ist.

    Die ursprüngliche Implementierung hat die nicht mehr existierende Methode
    ``WindowManager.update()`` verwendet und dadurch in Blender 4.4 einen
    ``AttributeError`` verursacht. Diese Version beobachtet lediglich die
    Markeranzahl über ein Zeitintervall und gibt ``True`` zurück, sobald sich
    etwas geändert hat, ansonsten ``False`` nach Ablauf des Timeouts.

    :param context: Aktueller Blender‑Kontext.
    :param timeout: Maximale Wartezeit in Sekunden.
    :return: ``True`` wenn sich die Anzahl der Marker geändert hat, sonst ``False``.
    """
    clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
    if not clip:
        print("[Fehler] Kein Clip aktiv.")
        return False

    def marker_count() -> int:
        return sum(len(track.markers) for track in clip.tracking.tracks)

    initial = marker_count()
    start_time = time.time()

    # Warte‑Schleife: prüft regelmäßig, ob sich die Markeranzahl geändert hat.
    while time.time() - start_time < timeout:
        if marker_count() != initial:
            return True
        # Kurze Pause, damit Blender Zeit zum Aktualisieren hat
        time.sleep(0.05)

    return False


def evaluate_tracking(context: bpy.types.Context):
    """Marker platzieren, dann Tracking & Fehlerberechnung."""
    try:
        bpy.ops.tracking.place_marker()
        if not wait_for_marker_change(context):
            print("[Abbruch] Markeranzahl hat sich nicht verändert.")
            return 0, float("inf"), 0
    except Exception as e:
        print(f"[Fehler] Marker-Platzierung fehlgeschlagen: {e}")
        return 0, float("inf"), 0

    # Fortsetzung NUR wenn Marker erfolgreich platziert wurden
    track_markers_until_end()
    error = error_value(context)

    length_info = get_tracking_lengths()
    if isinstance(length_info, dict):
        length = sum(v["length"] for v in length_info.values())
    else:
        length = float(length_info) if length_info else 0.0

    score = length / error if error else 0
    return length, error, score


def find_optimal_pattern(context: bpy.types.Context):
    """Finde bestes Pattern-Size Verhältnis."""
    clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
    if not clip:
        print("[Fehler] Kein aktiver Clip.")
        return None

    pattern = 1.0
    pattern_final = None
    bester_score = 0

    for _ in range(5):
        clip.tracking.settings.default_pattern_size = int(15 * pattern)
        clip.tracking.settings.default_search_size = int(15 * pattern * 2)
        _, _, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            pattern_final = pattern
        pattern += 0.25

    if pattern_final:
        clip.tracking.settings.default_pattern_size = int(15 * pattern_final)
        clip.tracking.settings.default_search_size = int(15 * pattern_final * 2)
    return pattern_final


def find_optimal_motion(context: bpy.types.Context):
    """Finde bestes Motion Model."""
    clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
    if not clip:
        print("[Fehler] Kein aktiver Clip.")
        return None

    modelle = ["Loc", "LocRot", "Affine"]
    bester_score = 0
    bestes_modell = None

    for modell in modelle:
        clip.tracking.settings.default_motion_model = modell
        _, _, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            bestes_modell = modell

    if bestes_modell:
        clip.tracking.settings.default_motion_model = bestes_modell
    return bestes_modell


def find_best_channel_combination(context: bpy.types.Context):
    """Testet Red-/Green-Kombinationen."""
    clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
    if not clip:
        print("[Fehler] Kein aktiver Clip.")
        return None

    kombis = [(True, False), (False, True), (True, True)]
    bester_score = 0
    beste_kombi = None

    for red, green in kombis:
        clip.tracking.settings.use_default_red_channel = red
        clip.tracking.settings.use_default_green_channel = green
        _, _, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            beste_kombi = (red, green)

    if beste_kombi:
        clip.tracking.settings.use_default_red_channel, clip.tracking.settings.use_default_green_channel = beste_kombi
    return beste_kombi


def run_tracking_optimization(context: bpy.types.Context):
    """
    Optimiert Pattern‑Größe, Motion‑Modelle und Farbkanäle nacheinander.

    Im ursprünglichen Ansatz wurden alle Varianten in schnellen Schleifen
    hintereinander getestet, während der Marker‑Platzierungsoperator
    asynchron (modal) ablief. Dadurch wurden mehrere Zyklen quasi parallel
    gestartet, was zu den mehrfachen "Deselektiere alle Marker"‑Meldungen
    führte. Diese Implementierung führt jeden Test sequenziell aus: Ein
    Versuch wird erst vollständig abgeschlossen, bevor der nächste beginnt.

    :param context: Der aktuelle Blender‑Kontext.
    :return: Ein Dictionary mit den bestbewerteten Parametern.
    """
    # Mögliche Werte für Pattern‑Skalierungen. Ausgangspunkt ist 1.0, die
    # Schritte entsprechen der früheren Schleife in find_optimal_pattern.
    pattern_sizes = [1.0 + 0.25 * i for i in range(5)]
    motion_models = ["Loc", "LocRot", "Affine"]
    channel_combinations = [(True, False), (False, True), (True, True)]

    results: dict[str, object] = {
        "pattern": None,
        "motion": None,
        "channels": None,
    }

    # Mustergrößen sequenziell testen
    best_pattern_score = -float("inf")
    best_pattern = None
    for p in pattern_sizes:
        clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
        if not clip:
            break
        clip.tracking.settings.default_pattern_size = int(15 * p)
        clip.tracking.settings.default_search_size = int(15 * p * 2)
        _length, _error, score = evaluate_tracking(context)
        if score > best_pattern_score:
            best_pattern_score = score
            best_pattern = p
    # Zurücksetzen auf bestes Pattern
    if best_pattern is not None:
        clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
        if clip:
            clip.tracking.settings.default_pattern_size = int(15 * best_pattern)
            clip.tracking.settings.default_search_size = int(15 * best_pattern * 2)
    results["pattern"] = best_pattern

    # Motion‑Modelle sequenziell testen
    best_motion_score = -float("inf")
    best_motion = None
    for model in motion_models:
        clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
        if not clip:
            break
        clip.tracking.settings.default_motion_model = model
        _length, _error, score = evaluate_tracking(context)
        if score > best_motion_score:
            best_motion_score = score
            best_motion = model
    # Zurücksetzen auf bestes Modell
    if best_motion is not None:
        clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
        if clip:
            clip.tracking.settings.default_motion_model = best_motion
    results["motion"] = best_motion

    # Kanal‑Kombinationen sequenziell testen
    best_channel_score = -float("inf")
    best_channel_combo = None
    for red, green in channel_combinations:
        clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
        if not clip:
            break
        clip.tracking.settings.use_default_red_channel = red
        clip.tracking.settings.use_default_green_channel = green
        _length, _error, score = evaluate_tracking(context)
        if score > best_channel_score:
            best_channel_score = score
            best_channel_combo = (red, green)
    # Zurücksetzen auf beste Kanäle
    if best_channel_combo is not None:
        clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
        if clip:
            clip.tracking.settings.use_default_red_channel, clip.tracking.settings.use_default_green_channel = best_channel_combo
    results["channels"] = best_channel_combo

    return results


def error_value(context):
    """Berechne Gesamtfehler aller Marker (Standardabweichung)."""
    clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
    if clip is None:
        return float("inf")

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
        return float("inf")

    def std_dev(values):
        mean_val = sum(values) / len(values)
        return (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5

    return std_dev(x_positions) + std_dev(y_positions)
