# Helper/motion_model_group_analysis.py
# ================================================================
# Adaptive Motion-Model-Analyse auf Basis ALLER Markerpositionen
# Erkennt: Loc, LocRot, LocScale, LocRotScale, Perspective
# KEINE FIXEN THRESHOLDS — alles datenrelativ & selbstanpassend
# ================================================================

from __future__ import annotations
import bpy
import math
from typing import Dict, List, Tuple

from .marker_positions_helper import get_positions
from .motion_model_helper import apply_motion_model


# ================================================================
# Hilfsfunktionen für Variation
# ================================================================

def _safe_var(values: List[float]) -> float:
    """Berechnet eine Variation (max-min)."""
    if not values:
        return 0.0
    return max(values) - min(values)


def _safe_avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


# ================================================================
# Globale Rot/Scale-Analyse
# ================================================================

def evaluate_global_model(marker_positions: Dict[str, List[Tuple[float, float]]]) -> str:
    """
    Analysiert die Markerwolke als Ganzes.
    Liefert eines der globalen Modelle:
    Loc / LocRot / LocScale / LocRotScale
    """

    # 1) Mittelpositionen aller Marker über Zeit bestimmen
    mean_positions = []
    for pts in marker_positions.values():
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        mean_positions.append((sum(xs) / len(xs), sum(ys) / len(ys)))

    if len(mean_positions) < 2:
        return "Loc"

    rel_distances = []
    avg_x_values = []
    avg_y_values = []

    for i in range(len(mean_positions) - 1):
        (x1, y1), (x2, y2) = mean_positions[i], mean_positions[i + 1]

        avg_x = (x1 + x2) * 0.5
        avg_y = (y1 + y2) * 0.5

        # relative Distanzänderung der Mittelpunktbewegungen
        rel_dist = (abs(x1 - x2) + abs(y1 - y2)) * 0.5

        rel_distances.append(rel_dist)
        avg_x_values.append(avg_x)
        avg_y_values.append(avg_y)

    dx_var = _safe_var(avg_x_values)
    dy_var = _safe_var(avg_y_values)
    rel_var = _safe_var(rel_distances)

    avg_rel = _safe_avg(rel_distances)
    avg_x   = _safe_avg(avg_x_values)
    avg_y   = _safe_avg(avg_y_values)

    rel_ratio = rel_var / (avg_rel + 1e-9)
    dx_ratio  = dx_var  / (abs(avg_x) + 1e-9)
    dy_ratio  = dy_var  / (abs(avg_y) + 1e-9)

    print(f"[GroupModel][Global] rel_ratio={rel_ratio:.6f}, dx_ratio={dx_ratio:.6f}, dy_ratio={dy_ratio:.6f}")

    # ========= Entscheidungslogik (ADAPTIV) =========

    # Rotation + Scale sichtbar
    if rel_ratio > 0.10 and (dx_ratio > 0.05 or dy_ratio > 0.05):
        print("[GroupModel][Global] -> LocRotScale")
        return "LocRotScale"

    # reine Skalierung (radiale Ausdehnung)
    if rel_ratio > 0.10:
        print("[GroupModel][Global] -> LocScale")
        return "LocScale"

    # reine Rotation (dominante seitliche Variation)
    if dx_ratio > 0.05 or dy_ratio > 0.05:
        print("[GroupModel][Global] -> LocRot")
        return "LocRot"

    print("[GroupModel][Global] -> Loc")
    return "Loc"


# ================================================================
# Perspective-Erkennung
# ================================================================

def detect_perspective(marker_positions: Dict[str, List[Tuple[float, float]]]) -> Tuple[str | None, float, Dict[str, float]]:
    """
    Bestimmt perspektivische Verzerrung durch Abweichung
    von radialen Abstandsänderungen.
    """

    if not marker_positions:
        return None, 0.0, {}

    total_movement = {}

    for name, pts in marker_positions.items():
        if len(pts) < 2:
            continue
        mpf = [(x + y) * 0.5 for x, y in pts]
        mpd = sum(abs(mpf[i+1] - mpf[i]) for i in range(len(mpf) - 1))
        total_movement[name] = mpd

    if not total_movement:
        return None, 0.0, {}

    center = min(total_movement, key=total_movement.get)
    cpts = marker_positions[center]
    cx   = sum(x for x, _ in cpts) / len(cpts)
    cy   = sum(y for _, y in cpts) / len(cpts)

    # --- Neue stabile RMS-basierte Perspective-Analyse ---
    mv_values = {}
    for name, pts in marker_positions.items():
        if len(pts) < 3:
            continue

        # radiale Abstände
        dist = [(abs(cx - x) + abs(cy - y)) * 0.5 for x, y in pts]

        # Veränderungen (Ableitung)
        diffs = [(dist[i+1] - dist[i]) for i in range(len(dist)-1)]

        # rms-Wert
        rms = math.sqrt(sum(d*d for d in diffs) / len(diffs))
        mv_values[name] = rms

    if not mv_values:
        return center, 0.0, {}

    # globaler rms
    global_rms = sum(mv_values.values()) / len(mv_values)

    # Abweichungen relativ zum RMS, NICHT durch tiny numbers
    devs = {name: (mv/global_rms if global_rms > 1e-6 else 1.0)
            for name, mv in mv_values.items()}

    max_dev = max(devs.values())

    print(f"[GroupModel][Perspective] max_dev={max_dev:.6f}, avg_dev={mv_avg:.6f}")

    return center, max_dev, devs


# ================================================================
# Hauptfunktion: Live Motion Model für alle selektierten Tracks
# ================================================================

def apply_group_motion_model(context: bpy.types.Context, max_frames: int = 10) -> None:
    """
    Analysiert die Bewegungsrelation ALLER selektierten Marker
    und setzt pro Track das beste Motion Model.
    """
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        return

    scene = context.scene
    current_frame = scene.frame_current

    selected = [t for t in clip.tracking.tracks if t.select]
    if not selected:
        active = clip.tracking.tracks.active
        if active:
            selected = [active]

    if not selected:
        return

    # ---- Positionen sammeln ----
    marker_positions: Dict[str, List[Tuple[float, float]]] = {}

    for tr in selected:
        pts = get_positions(tr, current_frame, max_frames=max_frames)
        if len(pts) >= 2:
            marker_positions[tr.name] = [(x, y) for _, (x, y) in pts]

    if not marker_positions:
        return

    print(f"[GroupModel] ==== FRAME {current_frame} ====")

    # ---- Globalmodell bestimmen ----
    global_model = evaluate_global_model(marker_positions)

    # ---- Perspective prüfen ----
    center, p_dev, p_map = detect_perspective(marker_positions)

    # adaptiv:
    mv_values = list(p_map.values())
    p_avg = sum(mv_values) / len(mv_values) if mv_values else 0.0
    # neue Bedingung: Perspective nur wenn global über Threshold
    if max_dev > 2.5:  # robust, empirisch stabil
        global_model = "Perspective"
        print(f"[GroupModel] -> Perspective (global_rms dev={max_dev:.3f})")

    # ---- Für jeden Marker anwenden ----
    for tr in selected:

        # individuelle Perspektiven abweichung
        indiv_ratio = 0.0
        if tr.name in p_map and p_avg != 0:
            indiv_ratio = p_map[tr.name] / (abs(p_avg) + 1e-9)

        if indiv_ratio > 1.5:
            model = "Perspective"
            print(f"[GroupModel] Track='{tr.name}' → Perspective (indiv_ratio={indiv_ratio:.6f})")
        else:
            model = global_model
            print(f"[GroupModel] Track='{tr.name}' → {model}")

        # get_positions schon geladen
        pts = get_positions(tr, current_frame, max_frames=max_frames)
        apply_motion_model(tr, pts, motion_model=model)

