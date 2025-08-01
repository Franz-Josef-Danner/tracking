from .track_markers_until_end import track_markers_until_end
from .test_marker_base import error_value
from .get_tracking_lengths import get_tracking_lengths

import bpy


__all__ = [
    "evaluate_tracking",
    "find_optimal_pattern",
    "find_optimal_motion",
    "find_best_channel_combination",
    "run_tracking_optimization",
    "error_value"
]


def evaluate_tracking(context: bpy.types.Context):
    """Durchführen von Detection, Tracking und Fehlerbewertung."""
    try:
        bpy.ops.tracking.place_marker('EXEC_DEFAULT')
    except Exception as e:
        print(f"[Fehler] Marker-Platzierung fehlgeschlagen: {e}")
        return 0, float("inf"), 0

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
    """Ermittelt die beste Pattern-Größe durch iteratives Vergrößern."""
    pattern = 1.0
    pattern_final = None
    bester_score = 0

    for i in range(5):
        context.scene.tracking_settings.pattern_size = int(15 * pattern)
        _, _, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            pattern_final = pattern
        pattern += 0.25

    if pattern_final:
        context.scene.tracking_settings.pattern_size = int(15 * pattern_final)
    return pattern_final


def find_optimal_motion(context: bpy.types.Context):
    """Durchläuft verschiedene Motion-Modelle und wählt das beste."""
    modelle = ["Loc", "LocRot", "Affine"]
    bester_score = 0
    bestes_modell = None

    for modell in modelle:
        context.scene.tracking_settings.motion_model = modell
        _, _, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            bestes_modell = modell

    if bestes_modell:
        context.scene.tracking_settings.motion_model = bestes_modell
    return bestes_modell


def find_best_channel_combination(context: bpy.types.Context):
    """Testet verschiedene Kombinationen von Tracking-Kanälen."""
    kombis = [(True, False), (False, True), (True, True)]
    bester_score = 0
    beste_kombi = None

    for red, green in kombis:
        context.scene.use_red_channel = red
        context.scene.use_green_channel = green
        _, _, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            beste_kombi = (red, green)

    if beste_kombi:
        context.scene.use_red_channel, context.scene.use_green_channel = beste_kombi
    return beste_kombi


def run_tracking_optimization(context: bpy.types.Context):
    """Führt alle Optimierungen in sinnvoller Reihenfolge durch."""
    pattern = find_optimal_pattern(context)
    motion = find_optimal_motion(context)
    channels = find_best_channel_combination(context)
    return {
        "pattern": pattern,
        "motion": motion,
        "channels": channels,
    }
