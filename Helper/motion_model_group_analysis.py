# Helper/motion_model_group_analysis.py
# ================================================================
# Adaptive Motion-Model-Analyse V2 (Cluster + Hysterese)
# Erkennt: Loc, LocRot, LocScale, LocRotScale, Perspective
# Keine fixen Thresholds – alles datenrelativ & selbstanpassend
# ================================================================

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import bpy

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
# Cluster: Core / Periphery / Outliers
# ================================================================

def _compute_total_motion(pts: List[Tuple[float, float]]) -> float:
    """Summierte Weglänge eines Markers über das Zeitfenster."""
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def _cluster_markers_by_motion(
    marker_positions: Dict[str, List[Tuple[float, float]]]
) -> Tuple[List[str], List[str], List[str]]:
    """
    Teilt Marker in drei Cluster:
    - core      : geringste Gesamtbewegung (≈ strukturelles Zentrum)
    - periphery : mittlere Bewegung (folgt Szene, aber nicht extrem)
    - outliers  : stärkste Bewegung (Parallaxe / Fehlerkandidaten)
    """
    if not marker_positions:
        return [], [], []

    motion_values = []
    for name, pts in marker_positions.items():
        m = _compute_total_motion(pts)
        motion_values.append((name, m))

    # nach Bewegungsmenge sortieren (aufsteigend)
    motion_values.sort(key=lambda x: x[1])

    n = len(motion_values)
    if n == 1:
        return [motion_values[0][0]], [], []

    core_n = max(1, int(round(n * 0.5)))
    outlier_n = max(0, int(round(n * 0.1)))
    periphery_n = max(0, n - core_n - outlier_n)

    core_names = [name for name, _ in motion_values[:core_n]]
    periphery_names = [name for name, _ in motion_values[core_n:core_n + periphery_n]]
    outlier_names = [name for name, _ in motion_values[core_n + periphery_n:]]

    return core_names, periphery_names, outlier_names


# ================================================================
# Globale Rot/Scale-Analyse (auf Basis der Core-Marker)
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
        if not xs or not ys:
            continue
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

    # ========= Entscheidungslogik (ADAPTIV) =========

    # Rotation + Scale sichtbar
    if rel_ratio > 0.10 and (dx_ratio > 0.05 or dy_ratio > 0.05):
        return "LocRotScale"

    # reine Skalierung (radiale Ausdehnung)
    if rel_ratio > 0.10:
        return "LocScale"

    # reine Rotation (dominante seitliche Variation)
    if dx_ratio > 0.05 or dy_ratio > 0.05:
        return "LocRot"

    return "Loc"


# ================================================================
# Perspective-Erkennung (RMS-basiert, robust)
# ================================================================

def detect_perspective(
    marker_positions: Dict[str, List[Tuple[float, float]]]
) -> Tuple[str | None, float, Dict[str, float], float]:
    """
    Bestimmt perspektivische Verzerrung durch Abweichung
    von radialen Abstandsänderungen.

    Rückgabe:
        center_name : Name des "ruhigsten" Markers
        max_dev     : maximale relative Abweichung (RMS-normalisiert)
        devs        : pro-Marker-Relativabweichungen
        mv_avg      : Durchschnitt der devs (für Logging / Ratio)
    """

    if not marker_positions:
        return None, 0.0, {}, 0.0

    total_movement: Dict[str, float] = {}

    # 1) Gesamtbewegung als Kriterium für "Mittelpunktkandidat"
    for name, pts in marker_positions.items():
        if len(pts) < 2:
            continue
        mpf = [(x + y) * 0.5 for x, y in pts]
        mpd = sum(abs(mpf[i + 1] - mpf[i]) for i in range(len(mpf) - 1))
        total_movement[name] = mpd

    if not total_movement:
        return None, 0.0, {}, 0.0

    center_name = min(total_movement, key=total_movement.get)
    cpts = marker_positions[center_name]
    cx   = sum(x for x, _ in cpts) / len(cpts)
    cy   = sum(y for _, y in cpts) / len(cpts)

    # 2) RMS-Analyse der radialen Abstandsänderung
    mv_values: Dict[str, float] = {}
    for name, pts in marker_positions.items():
        if len(pts) < 3:
            continue

        # radiale Abstände
        dist = [(abs(cx - x) + abs(cy - y)) * 0.5 for x, y in pts]

        # Veränderungen (Ableitung)
        diffs = [(dist[i + 1] - dist[i]) for i in range(len(dist) - 1)]

        # RMS-Wert
        rms = math.sqrt(sum(d * d for d in diffs) / len(diffs))
        mv_values[name] = rms

    if not mv_values:
        return center_name, 0.0, {}, 0.0

    global_rms = sum(mv_values.values()) / len(mv_values)

    devs: Dict[str, float] = {}
    for name, mv in mv_values.items():
        if global_rms > 1e-6:
            devs[name] = mv / global_rms
        else:
            devs[name] = 1.0

    dev_values = list(devs.values())
    max_dev = max(dev_values) if dev_values else 0.0
    mv_avg = sum(dev_values) / len(dev_values) if dev_values else 0.0

    # NEW: Standardabweichung für echte Differenzanalyse
    if len(dev_values) > 1:
        mean = mv_avg
        var = sum((v - mean) ** 2 for v in dev_values) / len(dev_values)
        p_std = math.sqrt(var)
    else:
        p_std = 0.0

    # Rückgabe erweitert um p_std
    return center_name, max_dev, devs, mv_avg, p_std

# ================================================================
# Hysterese-State (global + per Marker)
# ================================================================

_GLOBAL_STATE = {
    "last_frame": None,
    "raw_model": None,
    "effective_model": None,
    "stable_count": 0,
}

_MARKER_STATE: Dict[str, Dict[str, int]] = {}


def _apply_global_hysteresis(frame: int, raw_model: str) -> str:
    """Glättet das globale Modell über mehrere Frames."""
    st = _GLOBAL_STATE

    if st["raw_model"] == raw_model:
        st["stable_count"] += 1
    else:
        st["raw_model"] = raw_model
        st["stable_count"] = 1

    st["last_frame"] = frame

    if st["effective_model"] is None:
        st["effective_model"] = raw_model
        return raw_model

    # nur bei stabiler Wiederholung umschalten
    if st["stable_count"] >= 3 and st["effective_model"] != raw_model:
        st["effective_model"] = raw_model

    return st["effective_model"]


def _update_marker_perspective_state(
    name: str, wants_perspective: bool
) -> int:
    """
    Aktualisiert pro-Marker-Perspective-Hysterese.

    Rückgabe:
        Anzahl der aufeinanderfolgenden Frames,
        in denen der Marker als Perspective-Kandidat gesehen wurde.
    """
    state = _MARKER_STATE.get(name, {"persp_frames": 0})

    if wants_perspective:
        state["persp_frames"] += 1
    else:
        state["persp_frames"] = 0

    _MARKER_STATE[name] = state
    return state["persp_frames"]


def _cleanup_marker_state(active_names: List[str]) -> None:
    """Entfernt Marker aus dem State, die aktuell nicht mehr getrackt werden."""
    active_set = set(active_names)
    to_delete = [n for n in _MARKER_STATE.keys() if n not in active_set]
    for n in to_delete:
        del _MARKER_STATE[n]


# ================================================================
# Hauptfunktion: Live Motion Model für alle selektierten Tracks
# ================================================================

def apply_group_motion_model(context: bpy.types.Context, max_frames: int = 12) -> None:
    """
    Analysiert die Bewegungsrelation ALLER selektierten Marker
    und setzt pro Track das beste Motion Model (Loc / LocRot / LocScale /
    LocRotScale / Perspective), basierend auf:
        - Core/Periphery/Outlier-Clustern (Bewegungsmenge)
        - Globalem Modell (aus Core)
        - RMS-basierter Perspective-Analyse
        - Hysterese (global + pro Marker)
    """
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        return

    scene = context.scene
    current_frame = scene.frame_current

    # ---- Auswahl bestimmen ----
    selected = [t for t in clip.tracking.tracks if t.select]
    if not selected:
        active = clip.tracking.tracks.active
        if active:
            selected = [active]

    if not selected:
        return

    # ---- Positionen sammeln ----
    raw_positions: Dict[str, List[Tuple[int, Tuple[float, float]]]] = {}
    marker_positions_xy: Dict[str, List[Tuple[float, float]]] = {}

    for tr in selected:
        pts = get_positions(tr, current_frame, max_frames=max_frames)
        if len(pts) >= 2:
            raw_positions[tr.name] = pts
            marker_positions_xy[tr.name] = [(x, y) for _, (x, y) in pts]

    if not marker_positions_xy:
        return

    # ---- Clusterbildung nach Bewegungsmenge ----
    core_names, periphery_names, outlier_names = _cluster_markers_by_motion(
        marker_positions_xy
    )

    # Core-Subset für globales Modell
    core_positions = {
        name: marker_positions_xy[name]
        for name in core_names
        if name in marker_positions_xy
    }
    if len(core_positions) < 2:
        # Fallback: alle Marker verwenden
        core_positions = marker_positions_xy

    # ---- Globalmodell bestimmen (nur Core) ----
    global_model_raw = evaluate_global_model(core_positions)

    # ---- Perspective-Analyse (alle Marker) ----
    center_name, max_dev, p_map, mv_avg, p_std = detect_perspective(marker_positions_xy)

    # NEW: robuster globaler Perspective-Trigger
    # Nur wenn Ausreißer außerhalb 3*STD liegen und global keine reine Translation
    if p_std > 0.0:
        global_zscore = (max_dev - mv_avg) / (p_std + 1e-9)
        if global_zscore > 3.0 and global_model_raw != "Loc":
            global_model_raw = "Perspective"

    # ---- Hysterese auf globalem Modell ----
    effective_global = _apply_global_hysteresis(current_frame, global_model_raw)

    # ---- Marker-State aufräumen ----
    _cleanup_marker_state([tr.name for tr in selected])

    # ---- Pro Marker Modell bestimmen und anwenden ----
    dev_vals = list(p_map.values())
    p_avg = sum(dev_vals) / len(dev_vals) if dev_vals else 0.0

    cluster_map: Dict[str, str] = {}
    for n in core_names:
        cluster_map[n] = "core"
    for n in periphery_names:
        cluster_map[n] = "periphery"
    for n in outlier_names:
        cluster_map[n] = "outlier"

    for tr in selected:
        name = tr.name
        cluster = cluster_map.get(name, "core")

        # individuelle Perspective-Abweichung
        indiv_ratio = 0.0
        # NEW: Z-Score statt division durch mv_avg
        indiv_ratio = 0.0
        if name in p_map and p_std > 1e-9:
            indiv_ratio = (p_map[name] - mv_avg) / (p_std + 1e-9)

        # ---- Cluster-basierte Zielmodell-Wahl ----
        candidate_model = effective_global

        if effective_global == "Perspective":
            wants_perspective = True

        else:
            wants_perspective = False

        # NEW: Z-Score-basierte Regeln (Cluster-sensitiv, aber mathematisch korrekt)
        if cluster == "outlier":
            if indiv_ratio > 2.0:
                candidate_model = "Perspective"
                wants_perspective = True

        elif cluster == "periphery":
            if indiv_ratio > 2.5:
                candidate_model = "Perspective"
                wants_perspective = True

        else:  # core
            if indiv_ratio > 3.0:
                candidate_model = "Perspective"
                wants_perspective = True


        # ---- Per-Marker-Hysterese für Perspective ----
        persp_frames = _update_marker_perspective_state(name, wants_perspective)

        if candidate_model == "Perspective" and effective_global != "Perspective":
            # Perspective nur übernehmen, wenn 2 Frames in Folge
            if persp_frames >= 2:
                final_model = "Perspective"
            else:
                final_model = effective_global
        else:
            final_model = candidate_model

        # ---- Motion Model anwenden ----
        pts = raw_positions.get(name, [])
        apply_motion_model(tr, pts, motion_model=final_model)
