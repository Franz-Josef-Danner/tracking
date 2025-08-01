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


def wait_for_marker_change(context, timeout=0.5):
    """Warte bis sich die Markeranzahl verändert oder Timeout erreicht ist."""
    clip = getattr(context.space_data, "clip", None) or getattr(context.scene, "active_clip", None)
    if not clip:
        print("[Fehler] Kein Clip aktiv.")
        return False

    def marker_count():
        return sum(len(track.markers) for track in clip.tracking.tracks)

    initial = marker_count()
    start = time.time()

    while time.time() - start < timeout:
        bpy.context.window_manager.update()
        if marker_count() != initial:
            return True
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
    """Optimiert Pattern, Motion und Farbkanäle."""
    return {
        "pattern": find_optimal_pattern(context),
        "motion": find_optimal_motion(context),
        "channels": find_best_channel_combination(context),
    }


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
