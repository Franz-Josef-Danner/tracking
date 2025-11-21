# Helper.motion_average.py
from __future__ import annotations

import bpy
from typing import List, Tuple
import math

from .marker_positions_helper import get_positions

# ==========================================================
# Globale akkumulierte Werte
# ==========================================================
dx_var_accum = []
dy_var_accum = []
rel_var_accum = []
global_p_dev_accum = []
MAX_HISTORY = 10

# ----------------------------------------------------------
# Interner Helper: Frames-per-Track aus Szene lesen
# ----------------------------------------------------------
def _resolve_frames_per_track(scene: bpy.types.Scene, fallback: int = 5) -> int:
    value = None
    try:
        if hasattr(scene, "kaiserlich_frames_per_track"):
            value = getattr(scene, "kaiserlich_frames_per_track")
        elif "kaiserlich_frames_per_track" in scene:
            value = scene["kaiserlich_frames_per_track"]
    except Exception:
        value = None

    if value is None:
        value = fallback

    try:
        value = int(value)
    except Exception:
        value = fallback

    if value < 2:
        value = 2
    return value

def _evaluate_motion_model_pairwise(all_positions: list[tuple[float, float]],
                                    thresh_rot: float = 0.002,
                                    thresh_scale: float = 0.005,
                                    thresh_rot_scale_rot: float = 0.002,
                                    thresh_rot_scale_scale: float = 0.005) -> str:
    global dx_var_accum, dy_var_accum, rel_var_accum, MAX_HISTORY

    if len(all_positions) < 2:
        return "Loc"

    rel_distances = []
    avg_x_values = []
    avg_y_values = []

    for i in range(len(all_positions) - 1):
        (x1, y1), (x2, y2) = all_positions[i], all_positions[i + 1]
        avg_x_values.append((x1 + x2) / 2.0)
        avg_y_values.append((y1 + y2) / 2.0)
        rel_distances.append((abs(x1 - x2) + abs(y1 - y2)) / 2.0)

    if not rel_distances:
        return "Loc"

    dx_var = max(avg_x_values) - min(avg_x_values)
    dy_var = max(avg_y_values) - min(avg_y_values)
    rel_var = max(rel_distances) - min(rel_distances)

    dx_var_accum.append(dx_var)
    dy_var_accum.append(dy_var)
    rel_var_accum.append(rel_var)

    if len(dx_var_accum) > MAX_HISTORY: dx_var_accum.pop(0)
    if len(dy_var_accum) > MAX_HISTORY: dy_var_accum.pop(0)
    if len(rel_var_accum) > MAX_HISTORY: rel_var_accum.pop(0)

    dx_var_mean = sum(dx_var_accum) / len(dx_var_accum)
    dy_var_mean = sum(dy_var_accum) / len(dy_var_accum)
    rel_var_mean = sum(rel_var_accum) / len(rel_var_accum)

    # Klassifikation ohne Veränderung
    if (
        rel_var > thresh_rot_scale_scale
        and (dx_var > thresh_rot_scale_rot or dy_var > thresh_rot_scale_rot)
    ):
        return "LocRotScale"
    elif rel_var > thresh_scale:
        return "LocScale"
    elif dx_var > thresh_rot or dy_var > thresh_rot:
        return "LocRot"
    else:
        return "Loc"


# ==========================================================
# Perspective-Erkennung (Mittelpunktanalyse)
# ==========================================================

def _detect_perspective_motion(marker_positions: dict[str, list[tuple[float, float]]],
                               perspective_thresh: float = 0.002
                               ) -> tuple[str | None, float, dict[str, float]]:
    """
    Bestimmt Mittelpunkt-Marker und prüft perspektivische Abweichung.
    Rückgabe: (center_marker, max_dev, per_marker_dev_dict)
    - center_marker: Name des Markers mit geringster Gesamtbewegung
    - max_dev: größte Abweichung ggü. Mittelwert der mv_i über alle Marker
    - per_marker_dev_dict: Abweichung je Marker (für per-Marker-Perspective)
    """

    if not marker_positions:
        return None, 0.0, {}

    # 1) Bewegungslänge pro Marker (mpd_i)
    total_movement = {}
    for name, positions in marker_positions.items():
        if len(positions) < 2:
            continue
        mpf_values = [(x + y) / 2.0 for x, y in positions]
        mpd_i = sum(abs(mpf_values[i+1] - mpf_values[i]) for i in range(len(mpf_values) - 1))
        total_movement[name] = mpd_i

    if not total_movement:
        return None, 0.0, {}

    # 2) Mittelpunkt = Marker mit geringster Bewegung
    center_marker = min(total_movement, key=total_movement.get)
    center_positions = marker_positions[center_marker]
    mmx = sum(x for x, _ in center_positions) / len(center_positions)
    mmy = sum(y for _, y in center_positions) / len(center_positions)

    # 3) Abstände zum Mittelpunkt je Frame und deren Veränderung (mv_i)
    mv_values = {}
    for name, positions in marker_positions.items():
        if len(positions) < 2:
            continue
        md_list = [(abs(mmx - x) + abs(mmy - y)) / 2.0 for x, y in positions]
        mv_i = sum(md_list[i] - md_list[i + 1] for i in range(len(md_list) - 1))
        mv_values[name] = mv_i

    if not mv_values:
        return center_marker, 0.0, {}

    mvth = sum(abs(v) for v in mv_values.values()) / len(mv_values)

    # 4) Abweichungen je Marker
    per_marker_dev: dict[str, float] = {}
    for name, mv_i in mv_values.items():
        per_marker_dev[name] = abs(mv_i - mvth)

    max_dev = max(per_marker_dev.values()) if per_marker_dev else 0.0
    return center_marker, max_dev, per_marker_dev

# ==========================================================
# Hauptlogik – Hybrid-Auswertung + Perspective
# ==========================================================

def get_from_selected_tracks(
    context: bpy.types.Context,
    max_frames: int | None = None,
) -> None:
    global dx_var_accum, dy_var_accum, rel_var_accum, global_p_dev_accum, MAX_HISTORY
    """Analysiert Markerbewegung nur auf Basis der aktuell selektierten, nicht gemuteten Tracks
    und setzt daraus die Thresholds (Loc / LocRot / LocScale / LocRotScale / Perspective)."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return

    # ------------------------------------------------------
    # Nur selektierte UND nicht gemutete Tracks zulassen
    # ------------------------------------------------------
    selected_tracks = [
        t for t in clip.tracking.tracks
        if getattr(t, "select", False) and not getattr(t, "mute", False)
    ]

    # Fallback: nur aktiver Track, falls nicht gemutet
    if not selected_tracks:
        active = getattr(clip.tracking.tracks, "active", None)
        if active and not getattr(active, "mute", False):
            selected_tracks = [active]

    if not selected_tracks:
        return

    scene = context.scene
    current_frame = scene.frame_current

    # Frames-per-Track aus Szene beziehen (Fallback: max_frames oder 5)
    default_frames = max_frames if (max_frames is not None and max_frames > 0) else 5
    frames_per_track = _resolve_frames_per_track(scene, default_frames)

    # --- Markerpositionen sammeln ---
    marker_positions: dict[str, list[tuple[float, float]]] = {}
    for track in selected_tracks:
        positions = get_positions(
            track,
            current_frame,
            max_frames=frames_per_track,
        )
        # Mindestanzahl prüfen & Marker-Mute filtern
        if not positions or len(positions) < 2:
            continue

        valid_pts: list[tuple[float, float]] = []
        for frame, (x, y) in positions:
            marker = track.markers.find_frame(frame, exact=True)
            if marker and not getattr(marker, "mute", False):
                valid_pts.append((x, y))

        # Nur speichern, wenn nach Mute-Check mindestens 2 Punkte bleiben
        if len(valid_pts) >= 2:
            marker_positions[track.name] = valid_pts
    if not marker_positions:
        return

    try:
        # --- 1) Globales Modell aus Mittelwerten ---
        all_positions = []
        for pts in marker_positions.values():
            mean_x = sum(x for x, _ in pts) / len(pts)
            mean_y = sum(y for _, y in pts) / len(pts)
            all_positions.append((mean_x, mean_y))

        global_model = _evaluate_motion_model_pairwise(
            all_positions,
            getattr(scene, "kaiserlich_rot_thresh_x", 0.002),
            getattr(scene, "kaiserlich_scale_thresh_max", 0.005),
            getattr(scene, "kaiserlich_rot_scale_thresh_rot", 0.002),
            getattr(scene, "kaiserlich_rot_scale_thresh_scale", 0.005)
        )

        # --- 2) Perspective global & per Marker einmalig berechnen ---
        # Perspektive nur auf valide Tracks anwenden
        _, global_p_dev, per_marker_dev = _detect_perspective_motion(
            marker_positions,
            getattr(scene, "kaiserlich_perspective_thresh", 0.002)
        )
        perspective_thresh = getattr(scene, "kaiserlich_perspective_thresh", 0.002)
        
        global_p_dev_accum.append(global_p_dev)
        if len(global_p_dev_accum) > MAX_HISTORY: global_p_dev_accum.pop(0)
        global_p_dev_accum_mean = sum(global_p_dev_accum) / len(global_p_dev_accum)

        dx_var_mean = sum(dx_var_accum) / len(dx_var_accum) if dx_var_accum else 0.0
        dy_var_mean = sum(dy_var_accum) / len(dy_var_accum) if dy_var_accum else 0.0
        rel_var_mean = sum(rel_var_accum) / len(rel_var_accum) if rel_var_accum else 0.0

        # ============================================================
        # Aktuelle Motion Models der selektierten Tracks auslesen
        # und Anzahl je Typ in Szene-Variablen speichern
        # ============================================================
        model_counts = {
            "Loc": 0,
            "LocRot": 0,
            "LocScale": 0,
            "LocRotScale": 0,
            "Perspective": 0,
        }

        # Nur Tracks zählen, die valide Positionsdaten besitzen!
        for track in selected_tracks:
            if track.name not in marker_positions:
                continue  # kein positionsbasiertes Modell → ignorieren
            mm = getattr(track, "motion_model", None)
            if mm in model_counts:
                model_counts[mm] += 1

        # Zähler in Scene schreiben (Debug/Monitoring)
        for key, val in model_counts.items():
            scene[f"kaiserlich_model_count_{key}"] = val

        # Model-Counts auf lokale Variablen mappen
        loc = float(model_counts["Loc"])
        locrot = float(model_counts["LocRot"])
        locscale = float(model_counts["LocScale"])
        locrotscale = float(model_counts["LocRotScale"])
        persp = float(model_counts["Perspective"])

        if loc == 0:
            loc = 1
        if locrot == 0:
            locrot = 1
        if locscale == 0:
            locscale = 1
        if locrotscale == 0:
            locrotscale = 1
        if persp == 0:
            persp = 1


        mo_full = loc + locrot + locscale + locrotscale + persp
        
        # Anteile je Motion-Model
        share_loc = (1 / mo_full) * loc
        share_locrot = (1 / mo_full) * locrot
        share_locscale = (1 / mo_full) * locscale
        share_locrotscale = (1 / mo_full) * locrotscale
        share_persp = (1 / mo_full) * persp

        print("Motion Model Anteile:")
        print(" Loc:", share_loc)
        print(" LocRot:", share_locrot)
        print(" LocScale:", share_locscale) 
        print(" LocRotScale:", share_locrotscale)
        print(" Perspective:", share_persp)

        # Basisgrößen
        rel_var_min = rel_var_mean * 0.5
        d_var_com = (dx_var_mean + dy_var_mean) / 2.0
        rel_com = rel_var_mean * 0.25

        # gewichtende Faktoren je nach Verteilung der Motion Models
        dx_var_mean_mult = share_loc
        dy_var_mean_mult = share_loc
        rel_var_mean_mult = share_locrot
        rel_var_min_mult = share_locrot
        d_var_com_mult = share_locrotscale
        rel_com_mult = share_locrotscale
        global_p_dev_accum_mean_mult = share_persp

        th_prec = dx_var_mean + dy_var_mean + rel_var_mean + rel_var_min + d_var_com + rel_com + global_p_dev_accum_mean

        # anteile je THRESHOLD
        dx_var_perc = (1 / th_prec) * dx_var_mean
        dy_var_perc = (1 / th_prec) * dy_var_mean
        rel_var_mean_perc = (1 / th_prec) * rel_var_mean
        rel_var_min_perc = (1 / th_prec) * rel_var_min
        d_var_perc = (1 / th_prec) * d_var_com
        rel_perc = (1 / th_prec) * rel_com
        global_p_dev_accum_perc = (1 / th_prec) * global_p_dev_accum_mean
        print ("===================================================")
        print("Threshold Anteile:")
        print(" dx_var_perc:", dx_var_perc)
        print(" dy_var_perc:", dy_var_perc)
        print(" rel_var_mean_perc:", rel_var_mean_perc)
        print(" rel_var_min_perc:", rel_var_min_perc)
        print(" d_var_perc:", d_var_perc)
        print(" rel_perc:", rel_perc)
        print(" global_p_dev_accum_perc:", global_p_dev_accum_perc)

        # gewichtete Werte anwenden
        dx_var_mean = dx_var_mean * (dx_var_perc / dx_var_mean_mult)
        dy_var_mean = dy_var_mean * (dy_var_perc / dy_var_mean_mult)
        rel_var_mean = rel_var_mean * (rel_var_mean_perc / rel_var_mean_mult)
        rel_var_min = rel_var_min * (rel_var_min_perc / rel_var_min_mult)
        d_var_com = d_var_com * (d_var_perc / d_var_com_mult)
        rel_com = rel_com * (rel_perc / rel_com_mult)
        global_p_dev_accum_mean = global_p_dev_accum_mean * (global_p_dev_accum_perc / global_p_dev_accum_mean_mult)

        print ("===================================================")
        print("Angepasste Basisgrößen:")
        print(" dx_var_mean:", dx_var_mean)
        print(" dy_var_mean:", dy_var_mean)
        print(" rel_var_mean:", rel_var_mean)
        print(" rel_var_min:", rel_var_min)
        print(" d_var_com:", d_var_com)
        print(" rel_com:", rel_com)
        print(" global_p_dev_accum_mean:", global_p_dev_accum_mean)

        # Szene-Multiplikatoren und bisherige Maxima einlesen
        dx_var_multi = float(scene.get('dx_var_multi', 0.0))
        dy_var_multi = float(scene.get('dy_var_multi', 0.0))
        rel_var_multi = float(scene.get('rel_var_multi', 0.0))
        rel_var_multi_min = float(scene.get('rel_var_multi_min', 0.0))
        d_var_com_multi = float(scene.get('d_var_com_multi', 0.0))
        rel_com_multi = float(scene.get('rel_com_multi', 0.0))
        global_p_multi = float(scene.get('global_p_multi', 0.0))

        # Multiplikatoren mit Defaults initialisieren
        dx_var_scala = float(scene.get('dx_var_scala', 1.0))
        dy_var_scala = float(scene.get('dy_var_scala', 1.0))
        rel_var_scala = float(scene.get('rel_var_scala', 1.0))
        rel_var_min_scala = float(scene.get('rel_var_min_scala', 1.0))
        d_var_com_scala = float(scene.get('d_var_com_scala', 1.0))
        rel_com_scala = float(scene.get('rel_com_scala', 1.0))
        global_p_scala = float(scene.get('global_p_scala', 1.0))

        # skalierungs anteile anpassen, falls neue Maxima erreicht wurden
        if dx_var_multi < dx_var_mean:
            if dx_var_mean > 0:
                dx_var_multi = dx_var_mean
                dx_var_scala = 1.0 / dx_var_mean

        if dy_var_multi < dy_var_mean:
            if dy_var_mean > 0:
                dy_var_multi = dy_var_mean
                dy_var_scala = 1.0 / dy_var_mean

        if rel_var_multi < rel_var_mean:
            if rel_var_mean > 0:
                rel_var_multi = rel_var_mean
                rel_var_scala = 1.0 / rel_var_mean

        if rel_var_multi_min < rel_var_min:
            if rel_var_min > 0:
                rel_var_multi_min = rel_var_min
                rel_var_min_scala = 1.0 / rel_var_min

        if d_var_com_multi < d_var_com:
            if d_var_com > 0:
                d_var_com_multi = d_var_com
                d_var_com_scala = 1.0 / d_var_com

        if rel_com_multi < rel_com:
            if rel_com > 0:
                rel_com_multi = rel_com
                rel_com_scala = 1.0 / rel_com

        if global_p_multi < global_p_dev_accum_mean:
            if global_p_dev_accum_mean > 0:
                global_p_multi = global_p_dev_accum_mean
                global_p_scala = 1.0 / global_p_dev_accum_mean

        print ("===================================================")
        print("Aktuelle Maxima:")
        print("dx_var_multi:", dx_var_multi)
        print("dy_var_multi:", dy_var_multi)
        print("rel_var_multi:", rel_var_multi)
        print("rel_var_multi_min:", rel_var_multi_min)
        print("d_var_com_multi:", d_var_com_multi)
        print("rel_com_multi:", rel_com_multi)
        print("global_p_multi:", global_p_multi)

        # Multiplikatoren in Scene schreiben (inkl. Kompatibilitäts-Key für Scale)
        scene["dx_var_scala"] = dx_var_scala
        scene["dy_var_scala"] = dy_var_scala
        scene["rel_var_scala"] = rel_var_scala
        scene["srel_var_scala"] = rel_var_scala  # für formula_helper
        scene["rel_var_min_scala"] = rel_var_min_scala
        scene["d_var_com_scala"] = d_var_com_scala
        scene["rel_com_scala"] = rel_com_scala
        scene["global_p_scala"] = global_p_scala

        print ("===================================================")
        print("Aktuelle Skalierungsfaktoren:")
        print("dx_var_scala:", dx_var_scala)
        print("dy_var_scala:", dy_var_scala)
        print("rel_var_scala:", rel_var_scala)
        print("rel_var_min_scala:", rel_var_min_scala)
        print("d_var_com_scala:", d_var_com_scala)
        print("rel_com_scala:", rel_com_scala)
        print("global_p_scala:", global_p_scala)

        # finale Thresholds in Szene ablegen
        scene["kaiserlich_rot_thresh_x"] = dx_var_mean * dx_var_scala
        scene["kaiserlich_rot_thresh_y"] = dy_var_mean * dy_var_scala
        scene["kaiserlich_scale_thresh_min"] = rel_var_min * rel_var_min_scala
        scene["kaiserlich_scale_thresh_max"] = rel_var_mean * rel_var_scala
        scene["kaiserlich_rot_scale_thresh_rot"] = d_var_com * d_var_com_scala
        scene["kaiserlich_rot_scale_thresh_scale"] = rel_com * rel_com_scala
        scene["kaiserlich_perspective_thresh"] = global_p_dev_accum_mean * global_p_scala
        
        print ("===================================================")
        print ("kaiserlich_rot_thresh_x:", scene["kaiserlich_rot_thresh_x"])
        print ("kaiserlich_rot_thresh_y:", scene["kaiserlich_rot_thresh_y"])
        print ("kaiserlich_scale_thresh_min:", scene["kaiserlich_scale_thresh_min"])
        print ("kaiserlich_scale_thresh_max:", scene["kaiserlich_scale_thresh_max"])
        print ("kaiserlich_rot_scale_thresh_rot:", scene["kaiserlich_rot_scale_thresh_rot"])
        print ("kaiserlich_rot_scale_thresh_scale:", scene["kaiserlich_rot_scale_thresh_scale"])
        print ("kaiserlich_perspective_thresh:", scene["kaiserlich_perspective_thresh"])

    except Exception:
        pass
