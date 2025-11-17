# Helper.motion_average_backwards.py
from __future__ import annotations
import bpy
from typing import List, Tuple
from math import fsum

from .marker_positions_helper import get_positions
from .motion_model_helper import apply_motion_model

# ==========================================================
# Globale akkumulierte Werte
# ==========================================================
dx_var_accum: list[float] = []
dy_var_accum: list[float] = []
rel_var_accum: list[float] = []
global_p_dev_accum: list[float] = []
MAX_HISTORY = 10


# ==========================================================
# Motion-Model Analyse (Backward)
# ==========================================================
def _evaluate_motion_model_pairwise_backwards(
    all_positions: list[tuple[float, float]],
    thresh_rot: float,
    thresh_scale: float,
    thresh_rot_scale_rot: float,
    thresh_rot_scale_scale: float
) -> str:

    if len(all_positions) < 2:
        return "Loc"

    # Reihenfolge umkehren
    pts = list(reversed(all_positions))

    avg_x_values = []
    avg_y_values = []
    rel_distances = []

    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
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

    dx_avg = sum(dx_var_accum) / len(dx_var_accum)
    dy_avg = sum(dy_var_accum) / len(dy_var_accum)
    rel_avg = sum(rel_var_accum) / len(rel_var_accum)
    print(f"[MotionModel][AVG10] dx={dx_avg:.6f} dy={dy_avg:.6f} rel={rel_avg:.6f}")

    if rel_var > thresh_rot_scale_scale and (dx_var > thresh_rot_scale_rot or dy_var > thresh_rot_scale_rot):
        return "LocRotScale"
    elif rel_var > thresh_scale:
        return "LocScale"
    elif dx_var > thresh_rot or dy_var > thresh_rot:
        return "LocRot"
    else:
        return "Loc"


# ==========================================================
# Perspective-Erkennung (Backward) – richtungsneutral
# ==========================================================
def _detect_perspective_motion_backwards(
    marker_positions: dict[str, list[tuple[float, float]]],
    perspective_thresh: float
) -> tuple[str | None, float, dict[str, float]]:

    if not marker_positions:
        return None, 0.0, {}

    mp_rev = {name: list(reversed(pts)) for name, pts in marker_positions.items()}

    # Bewegungssumme pro Marker
    total_move = {}
    for name, pts in mp_rev.items():
        if len(pts) < 2: continue
        means = [(x + y) / 2.0 for x, y in pts]
        total_move[name] = sum(abs(means[i+1] - means[i]) for i in range(len(means)-1))

    if not total_move:
        return None, 0.0, {}

    # Mittelpunktsteuerung
    center = min(total_move, key=total_move.get)
    center_pts = mp_rev[center]
    mmx = fsum(x for x,_ in center_pts)/len(center_pts)
    mmy = fsum(y for _,y in center_pts)/len(center_pts)

    mv_values = {}
    for name, pts in mp_rev.items():
        if len(pts) < 2: continue
        dist = [(abs(mmx-x)+abs(mmy-y))/2.0 for x,y in pts]
        mv = sum(abs(dist[i+1]-dist[i]) for i in range(len(dist)-1))
        mv_values[name] = mv

    if not mv_values:
        return center, 0.0, {}

    mv_mean = sum(mv_values.values())/len(mv_values)
    per_dev = {n: abs(v - mv_mean) for n,v in mv_values.items()}
    max_dev = max(per_dev.values())

    return center, max_dev, per_dev


# ==========================================================
# Hauptlogik – rückwärts Motion-Modeling
# ==========================================================
def get_from_selected_tracks_backwards(
    context: bpy.types.Context,
    max_frames: int = 10
) -> None:

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return

    tracks = [t for t in clip.tracking.tracks if t.select] or \
             [clip.tracking.tracks.active] or []

    if not tracks:
        return

    scene = context.scene
    # Sicherstellen, dass Frame IMMER int ist
    cf = int(scene.frame_current)
    scene.frame_current = cf
    context.space_data.clip_user.frame_current = cf

    marker_positions = {}
    for tr in tracks:
        # Sicherstellen, dass Frame immer INT ist
        # Frame ist garantiert INT → direkte Verwendung
        pos = get_positions(tr, cf, max_frames=max_frames)
        pos = [(int(f), (float(x), float(y))) for f, (x, y) in pos]
        if len(pos) >= 2:
            marker_positions[tr.name] = [(x,y) for _,(x,y) in pos]

    if not marker_positions:
        return

    try:
        # Globalmodell
        means = [(sum(x for x,_ in pts)/len(pts), sum(y for _,y in pts)/len(pts))
                 for pts in marker_positions.values()]

        global_model = _evaluate_motion_model_pairwise_backwards(
            means,
            scene.kaiserlich_rot_thresh_x/100000.0,
            scene.kaiserlich_scale_thresh_max/100000.0,
            scene.kaiserlich_rot_scale_thresh_rot/100000.0,
            scene.kaiserlich_rot_scale_thresh_scale/100000.0
        )

        _, g_dev, per_dev = _detect_perspective_motion_backwards(
            marker_positions,
            scene.kaiserlich_perspective_thresh/1000000.0
        )

        global_p_dev_accum.append(g_dev)
        if len(global_p_dev_accum) > MAX_HISTORY: global_p_dev_accum.pop(0)
        gp_mean = sum(global_p_dev_accum)/len(global_p_dev_accum)

        print(f"[Perspective][AVG10] global_p_dev={gp_mean:.6f}")

        # Basis → Modell pro Track
        p_thresh = scene.kaiserlich_perspective_thresh/1000000.0
        if gp_mean > p_thresh:
            global_model = "Perspective"

        for tr in tracks:
            # Frame unverändert INT
            local_positions = get_positions(tr, cf, max_frames=max_frames)
            # Frame-Cast → int
            local_positions = [(int(f), (float(x), float(y))) for f, (x, y) in local_positions]
            pts = [(x, y) for _, (x, y) in local_positions]

            if len(pts) < 2: continue

            local = _evaluate_motion_model_pairwise_backwards(
                pts,
                scene.kaiserlich_rot_thresh_x/100000.0,
                scene.kaiserlich_scale_thresh_max/100000.0,
                scene.kaiserlich_rot_scale_thresh_rot/100000.0,
                scene.kaiserlich_rot_scale_thresh_scale/100000.0
            )

            dev = per_dev.get(tr.name, 0.0)
            model = "Perspective" if (global_model == "Perspective" or dev > p_thresh) else local
            apply_motion_model(tr, pts, model)

    except Exception as e:
        print(f"[BackwardMotion][ERROR] {e}")
