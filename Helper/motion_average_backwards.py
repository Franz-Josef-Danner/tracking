# Helper.motion_average.py
# ==========================================================
# Motion-Model-Analyse für Blender-Tracking (Forward-Version)
# ==========================================================
#
# Diese Datei analysiert Markerbewegungen und klassifiziert
# das globale Bewegungsmodell der Kamera/Markersituation:
#
#   Loc            → reine Translation
#   LocRot         → Translation + leichte Rotation
#   LocScale       → Translation + Skalierung (Zoom-Effekt)
#   LocRotScale    → kombiniertes komplexes Modell
#   Perspective    → perspektivische Tiefenverschiebung (falls erkannt)
#
# Die Analyse basiert auf fortlaufend gemittelten Abweichungen
# über mehrere Frames (Gleitfenster = 10 Frames).
#
# Warnung:
# - Das System ist vollständig datengetrieben → Junk-Input erzeugt Junk-Output.
# - Jede Frame-Iteration bricht das Tracking ggf. um → Performance kostet.
# - Die Metriken sind rein 2D-basiert → robust für Film-Tracking,
#   aber kein absoluter Tiefen-Indikator ohne Solve.
#
# ==========================================================

from __future__ import annotations

import bpy
from typing import List, Tuple, Dict
import math

from .marker_positions_helper import get_positions

# ==========================================================
# Globale akkumulierte Werte
# ----------------------------------------------------------
# Diese Werte glätten Frame-weise Mess-Schwankungen.
# Die History wird konstant gehalten (MAX_HISTORY Frames).
# ==========================================================
dx_var_accum: List[float] = []   # horizontale Streuung
dy_var_accum: List[float] = []   # vertikale Streuung
rel_var_accum: List[float] = []  # Streuung relativer Distanzen (Zoom-Indikator)
global_p_dev_accum: List[float] = []  # perspektivische Abweichung global

MAX_HISTORY: int = 10  # Gleitfenstergröße


# ==========================================================
# Bewegungsmodell-Evaluierung (Paarvergleich)
# ----------------------------------------------------------
# INPUT: Mittelpunkte aller ausgewerteten Marker
# OUTPUT: Motion-Model-String
#
# Schwellenwerte werden kontinuierlich dynamisch gesetzt.
# ==========================================================
def _evaluate_motion_model_pairwise(
    all_positions: list[tuple[float, float]],
    thresh_rot: float = 0.002,
    thresh_scale: float = 0.005,
    thresh_rot_scale_rot: float = 0.002,
    thresh_rot_scale_scale: float = 0.005,
) -> str:
    """
    Bewertet das globale Bewegungsmuster anhand mittlerer
    Markerpositionsverschiebungen zwischen Frame-Paaren.
    """

    global dx_var_accum, dy_var_accum, rel_var_accum

    # Unzureichende Daten → minimale Annahme
    if len(all_positions) < 2:
        return "Loc"

    rel_distances: list[float] = []
    avg_x_values: list[float] = []
    avg_y_values: list[float] = []

    for i in range(len(all_positions) - 1):
        # Zwei aufeinanderfolgende Schwerpunkt-Positionen
        (x1, y1), (x2, y2) = all_positions[i], all_positions[i + 1]

        avg_x_values.append((x1 + x2) / 2.0)
        avg_y_values.append((y1 + y2) / 2.0)

        rel_distances.append((abs(x1 - x2) + abs(y1 - y2)) / 2.0)

    if not rel_distances:
        return "Loc"


    # Variationsmaße (Streuung = Indikator für Rotation/Scale)
    dx_var = max(avg_x_values) - min(avg_x_values)
    dy_var = max(avg_y_values) - min(avg_y_values)
    rel_var = max(rel_distances) - min(rel_distances)

    dx_var_accum.append(dx_var)
    dy_var_accum.append(dy_var)
    rel_var_accum.append(rel_var)

    # Historie begrenzen (gleitendes Mittel)
    if len(dx_var_accum) > MAX_HISTORY: dx_var_accum.pop(0)
    if len(dy_var_accum) > MAX_HISTORY: dy_var_accum.pop(0)
    if len(rel_var_accum) > MAX_HISTORY: rel_var_accum.pop(0)

    dx_var_mean = sum(dx_var_accum) / len(dx_var_accum)
    dy_var_mean = sum(dy_var_accum) / len(dy_var_accum)
    rel_var_mean = sum(rel_var_accum) / len(rel_var_accum)

    print(f"[MotionModel][AVG10] dx={dx_var_mean:.6f} dy={dy_var_mean:.6f} rel={rel_var_mean:.6f}")

    # ======================================================
    # Modellklassifikation (Priorität: Komplex → Einfach)
    # ======================================================
    if (
        rel_var > thresh_rot_scale_scale
        and (dx_var > thresh_rot_scale_rot or dy_var > thresh_rot_scale_rot)
    ):
        return "LocRotScale"   # Rotation + Skalierung
    elif rel_var > thresh_scale:
        return "LocScale"      # Camera-Zoom
    elif dx_var > thresh_rot or dy_var > thresh_rot:
        return "LocRot"        # leichte Rotation
    else:
        return "Loc"           # reine Translation


# ==========================================================
# 2,5D-Heuristik: Perspektivische Tiefenerkennung
# ----------------------------------------------------------
# Globale Identifikation einer Tiefenbewegung:
#   Marker weit vom Mittelpunkt bewegen sich stärker
#   → Indikator für Perspektive
# ==========================================================
def _detect_perspective_motion(
    marker_positions: Dict[str, List[tuple[float, float]]],
    perspective_thresh: float = 0.002,
) -> tuple[str | None, float, Dict[str, float]]:
    """
    Analysiert perspektivische Verzerrungen über Markergruppen.
    Rückgabe:
    - Markername mit geringster Bewegung (Mittelpunkt-Anker)
    - Maximal erkannte Perspektiven-Abweichung
    - Abweichungen je Marker zur Debug-Analyse
    """

    if not marker_positions:
        return None, 0.0, {}

    # Gesamtbewegung pro Marker (Translationslänge)
    total_movement: Dict[str, float] = {}
    for name, positions in marker_positions.items():
        if len(positions) < 2: continue
        mpf = [(x + y) / 2.0 for x, y in positions]  # 1D-Projektionswert
        total_movement[name] = sum(abs(mpf[i+1] - mpf[i]) for i in range(len(mpf) - 1))

    if not total_movement:
        return None, 0.0, {}

    # Mittelpunktmarker = stabilster Marker
    center_marker = min(total_movement, key=total_movement.get)
    center_positions = marker_positions[center_marker]

    # Mittelpunktkoordinaten
    mmx = sum(x for x, _ in center_positions) / len(center_positions)
    mmy = sum(y for _, y in center_positions) / len(center_positions)

    # Abweichung vom Mittelpunkt über Zeit
    mv_values: Dict[str, float] = {}
    for name, positions in marker_positions.items():
        if len(positions) < 2: continue
        dist = [(abs(mmx - x) + abs(mmy - y)) / 2.0 for x, y in positions]
        mv_values[name] = sum(dist[i] - dist[i + 1] for i in range(len(dist) - 1))

    if not mv_values:
        return center_marker, 0.0, {}

    # durchschnittlicher Bewegungstrend
    mv_thresh = sum(abs(v) for v in mv_values.values()) / len(mv_values)

    per_marker_dev = {name: abs(mv - mv_thresh) for name, mv in mv_values.items()}
    max_dev = max(per_marker_dev.values()) if per_marker_dev else 0.0

    return center_marker, max_dev, per_marker_dev


# ==========================================================
# Hauptlogik – Hybrid-Bewertung + Adaptive Schwellenwerte
# ==========================================================
def get_from_selected_tracks(context: bpy.types.Context, max_frames: int = 10) -> None:
    """
    Führt globale Motion-Analyse aus:
    - Hybrid Loc/Rot/Scale-Modell aus Marker-Mittelwerten
    - Perspektiv-Analyse zur Tiefenindikation
    - Dynamische Update der Schwellenwerte im Scene-State
    """

    global global_p_dev_accum

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return

    # Track-Selektion: wenn nichts ausgewählt → aktiver Track
    selected_tracks = [t for t in clip.tracking.tracks if t.select] \
                      or ([clip.tracking.tracks.active] if clip.tracking.tracks.active else [])

    if not selected_tracks:
        return

    scene = context.scene
    current_frame = scene.frame_current

    # Markerpositionen sammeln (nur Marker mit Historie)
    marker_positions: Dict[str, List[tuple[float, float]]] = {}
    for track in selected_tracks:
        positions = get_positions(track, current_frame, max_frames=max_frames)
        if len(positions) >= 2:
            marker_positions[track.name] = [(x, y) for _, (x, y) in positions]

    if not marker_positions:
        return

    try:
        # --- Globales Bewegungsmodell ---
        all_positions = []
        for pts in marker_positions.values():
            mean_x = sum(x for x, _ in pts) / len(pts)
            mean_y = sum(y for _, y in pts) / len(pts)
            all_positions.append((mean_x, mean_y))

        _evaluate_motion_model_pairwise(
            all_positions,
            getattr(scene, "kaiserlich_rot_thresh_x", 0.002),
            getattr(scene, "kaiserlich_scale_thresh_max", 0.005),
            getattr(scene, "kaiserlich_rot_scale_thresh_rot", 0.002),
            getattr(scene, "kaiserlich_rot_scale_thresh_scale", 0.005),
        )

        # --- Perspektive bewerten ---
        _, global_p_dev, per_marker_dev = _detect_perspective_motion(
            marker_positions,
            getattr(scene, "kaiserlich_perspective_thresh", 0.002),
        )

        global_p_dev_accum.append(global_p_dev)
        if len(global_p_dev_accum) > MAX_HISTORY: global_p_dev_accum.pop(0)
        global_p_dev_accum_mean = sum(global_p_dev_accum) / len(global_p_dev_accum)

        print(f"[Perspective][AVG10] global_p_dev={global_p_dev_accum_mean:.6f}")

        # ======================================================
        # Dynamische Schwellenwert-ADAPTATION
        # → je nach Material & Fehlerverhalten
        # ======================================================
        dx_var_mean = sum(dx_var_accum) / len(dx_var_accum) if dx_var_accum else 0.0
        dy_var_mean = sum(dy_var_accum) / len(dy_var_accum) if dy_var_accum else 0.0
        rel_var_mean = sum(rel_var_accum) / len(rel_var_accum) if rel_var_accum else 0.0

        # Formel empirisch optimiert – nicht theoretisch “schön”
        scene["kaiserlich_rot_thresh_x"] = (dx_var_mean / 250) * 100000
        scene["kaiserlich_rot_thresh_y"] = (dy_var_mean / 250) * 100000
        scene["kaiserlich_scale_thresh_max"] = (rel_var_mean / 1000) * 100000
        scene["kaiserlich_scale_thresh_min"] = (rel_var_mean / 500) * 100000
        scene["kaiserlich_rot_scale_thresh_rot"] = (((dx_var_mean/250)+(dy_var_mean/250))/2)*100000
        scene["kaiserlich_rot_scale_thresh_scale"] = (rel_var_mean / 750) * 100000
        scene["kaiserlich_perspective_thresh"] = min(1000, (global_p_dev_accum_mean / 10) * 1000000)

    except Exception as e:
        print(f"[MotionModel][ERROR] {e}")
        return
