"""Automatischer Optimierungszyklus für das Tracking.

Dieses Modul nutzt mehrere bereits vorhandene Helferfunktionen um in drei
Stufen optimale Einstellungen zu finden:
- Pattern-Größe
- Motion-Model
- Farbkanal Kombinationen
"""

from __future__ import annotations

import bpy

from ..operators import place_marker_operator
from .track_markers_until_end import track_markers_until_end
from .get_tracking_lengths import get_tracking_lengths
from .cycle_motion_model import cycle_motion_model
from .set_tracking_channels import set_tracking_channels


# fallback error calculation if not provided by module
try:
    from ..operators.error_value_operator import error_value  # type: ignore
except Exception:  # pragma: no cover - optional import
    def error_value(context: bpy.types.Context) -> float:
        """Return the total error of all selected tracks."""
        clip = context.space_data.clip if context.space_data else None
        if clip is None:
            return 0.0
        x_pos, y_pos = [], []
        for track in clip.tracking.tracks:
            if not track.select:
                continue
            for marker in track.markers:
                if marker.mute:
                    continue
                x_pos.append(marker.co[0])
                y_pos.append(marker.co[1])
        if not x_pos:
            return 0.0
        mean_x = sum(x_pos) / len(x_pos)
        mean_y = sum(y_pos) / len(y_pos)
        dev_x = sum((x - mean_x) ** 2 for x in x_pos) / len(x_pos)
        dev_y = sum((y - mean_y) ** 2 for y in y_pos) / len(y_pos)
        return (dev_x ** 0.5) + (dev_y ** 0.5)


def evaluate_tracking(context: bpy.types.Context):
    """Durchführen von Detection, Tracking und Fehlerbewertung."""
    if hasattr(place_marker_operator, "detect"):
        place_marker_operator.detect(context)
    else:
        operator_start = place_marker_operator.TRACKING_OT_place_marker_start()
        operator_start.execute(context)
        operator_continue = (
            place_marker_operator.TRACKING_OT_place_marker_continue()
        )
        operator_continue.execute(context)

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
    """Ermittelt die beste Pattern-Größe."""
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
            wiederholungen = 0
        else:
            wiederholungen += 1
            if wiederholungen > max_wiederholungen:
                break
        pattern *= 1.1

    return pattern_final


def find_optimal_motion(context: bpy.types.Context):
    """Bestimmt das optimal passende Motion-Model."""
    motion = 1.0
    motion_final = None
    bester_score = 0.0

    for _ in range(7):
        length, error, score = evaluate_tracking(context)
        if score > bester_score:
            bester_score = score
            motion_final = motion
        cycle_motion_model()

    return motion_final


def find_best_channel_combination(context: bpy.types.Context):
    """Finde die beste Farbkanal-Kombination."""
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
    """Starte den kompletten Optimierungszyklus."""
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

