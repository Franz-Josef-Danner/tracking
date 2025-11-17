# Helper.motion_average_backwards.py
from __future__ import annotations

import bpy
from typing import List, Tuple
import math

from .marker_positions_helper import get_positions
from .motion_model_helper import apply_motion_model


# ==========================================================
# Pairwise-Analyse (REVERSE Processing)
# ==========================================================
def _evaluate_motion_model_pairwise_backwards(
    all_positions: list[tuple[float, float]],
    thresh_rot: float = 0.002,
    thresh_scale: float = 0.005,
    thresh_rot_scale_rot: float = 0.002,
    thresh_rot_scale_scale: float = 0.005,
) -> str:

    if len(all_positions) < 2:
        return "Loc"

    # Sequenz rückwärts werten
    all_positions = list(reversed(all_positions))

    rel_distances = []
    avg_x_values = []
    avg_y_values = []

    for i in range(len(all_positions) - 1):
        (x1, y1), (x2, y2) = all_positions[i], all_positions[i + 1]
        avg_x = (x1 + x2) / 2.0
        avg_y = (y1 + y2) / 2.0
        rel_dist = (abs(x1 - x2) + abs(y1 - y2)) / 2.0

        avg_x_values.append(avg_x)
        avg_y_values.append(avg_y)
        rel_distances.append(rel_dist)

    if not rel_distances:
        return "Loc"

    dx_var = max(avg_x_values) - min(avg_x_values)
    dy_var = max(avg_y_values) - min(avg_y_values)
    rel_var = max(rel_distances) - min(rel_distances)

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
# Perspective-Analyse REVERSE
# ==========================================================
def _detect_perspective_motion_backwards(
    marker_positions: dict[str, list[tuple[float, float]]],
    perspective_thresh: float = 0.002
) -> tuple[str | None, float, dict[str, float]]:

    # kopieren + reverse für jeden Marker
    mp_rev = {n: list(reversed(p)) for n, p in marker_positions.items()}
    from math import fsum

    if not mp_rev:
        return None, 0.0, {}

    # identische Logik → nur rückwärts Datenbasis
    total_movement = {}
    for name, positions in mp_rev.items():
        if len(positions) < 2:
            continue
        mpf = [(x + y) / 2.0 for x, y in positions]
        mpd_i = sum(abs(mpf[i+1] - mpf[i]) for i in range(len(mpf)-1))
        total_movement[name] = mpd_i

    if not total_movement:
        return None, 0.0, {}

    center_marker = min(total_movement, key=total_movement.get)
    center_positions = mp_rev[center_marker]
    mmx = fsum(x for x,_ in center_positions)/len(center_positions)
    mmy = fsum(y for _,y in center_positions)/len(center_positions)

    mv_values = {}
    for name, positions in mp_rev.items():
        if len(positions) < 2:
            continue
        md_list = [(abs(mmx-x)+abs(mmy-y))/2.0 for x,y in positions]
        mv_i = sum(md_list[i] - md_list[i+1] for i in range(len(md_list)-1))
        mv_values[name] = mv_i

    if not mv_values:
        return center_marker, 0.0, {}

    mvth = sum(abs(v) for v in mv_values.values()) / len(mv_values)

    per_marker_dev = {n: abs(v - mvth) for n, v in mv_values.items()}
    max_dev = max(per_marker_dev.values()) if per_marker_dev else 0.0
    return center_marker, max_dev, per_marker_dev


# ==========================================================
# Hauptlogik – rückwärts Motion-Modeling
# ==========================================================
def apply_formula_on_selected_tracks_backwards(
    context: bpy.types.Context,
    max_frames: int = 10
) -> None:

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return

    tracks = [t for t in clip.tracking.tracks if t.select]
    if not tracks:
        at = clip.tracking.tracks.active
        if at:
            tracks = [at]
    if not tracks:
        return

    scene = context.scene
    # Sicherstellen, dass Frame IMMER INT ist
    current_frame = int(scene.frame_current)

    marker_positions = {}
    for tr in tracks:
        pos = get_positions(tr, current_frame, max_frames=max_frames)
        # Frame-Cast → int
        pos = [(int(f), (float(x), float(y))) for f, (x, y) in pos]
        if len(pos) >= 2:
            marker_positions[tr.name] = [(x, y) for _, (x, y) in pos]

    if not marker_positions:
        return

    try:
        # globaler Mittelwert über Marker
        all_positions = []
        for pts in marker_positions.values():
            mx = sum(x for x,_ in pts)/len(pts)
            my = sum(y for _,y in pts)/len(pts)
            all_positions.append((mx, my))

        global_model = _evaluate_motion_model_pairwise_backwards(
            all_positions,
            scene.kaiserlich_rot_thresh_x / 100000.0,
            scene.kaiserlich_scale_thresh_max / 100000.0,
            scene.kaiserlich_rot_scale_thresh_rot / 100000.0,
            scene.kaiserlich_rot_scale_thresh_scale / 100000.0
        )

        _, global_p_dev, per_marker_dev = _detect_perspective_motion_backwards(
            marker_positions,
            scene.kaiserlich_perspective_thresh / 1000000.0
        )
        persp_thresh = scene.kaiserlich_perspective_thresh / 1000000.0
        if global_p_dev > persp_thresh:
            global_model = "Perspective"

        # pro Marker anwenden
        for tr in tracks:
        pos = get_positions(tr, current_frame, max_frames=max_frames)
        pos = [(int(f), (float(x), float(y))) for f, (x, y) in pos]
        if len(pos) < 2:
            continue

            local = _evaluate_motion_model_pairwise_backwards(
                [(x,y) for _,(x,y) in pos],
                scene.kaiserlich_rot_thresh_x / 100000.0,
                scene.kaiserlich_scale_thresh_max / 100000.0,
                scene.kaiserlich_rot_scale_thresh_rot / 100000.0,
                scene.kaiserlich_rot_scale_thresh_scale / 100000.0
            )

            dev = per_marker_dev.get(tr.name, 0.0)
            model = "Perspective" if (global_model=="Perspective" or dev>persp_thresh) else local

            apply_motion_model(tr, pos, motion_model=model)

    except Exception as e:
        print(f"[BackwardMotion] ERROR: {e}")
