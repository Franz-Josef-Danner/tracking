# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/seeding.py – Stufenweises Seeding (/5-Logik) mit Dedup und Feedback

Stages: threshold in {1.0, 0.1, 0.01, 0.001, 0.0001}
Pattern/α je Stufe gemäß Spezifikation (clamp 9..41, α∈[2..4])
Dedup: Distanz-basierte Bereinigung gg. Baseline (bestehende + bereits akzeptierte Marker)
Anzahlsteuerung: per_stage-Band ±10 %, Feedback via min_distance
"""
from __future__ import annotations

from typing import Dict, Any, List, Set, Tuple

from .governance import LIMITS
from .init_params import _round_even
from .strm import ROI
from . import detect as detect_mod
from . import distanze as dist_mod

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore

__all__ = ("staged_detect_with_dedup",)


def _get_tracks_ptrs_with_marker_on_frame(clip, frame: int) -> Set[int]:
    s: Set[int] = set()
    try:
        for tr in clip.tracking.tracks:
            try:
                m = tr.markers.find_frame(frame, exact=True)
            except TypeError:
                m = tr.markers.find_frame(frame)
            if m:
                s.add(int(tr.as_pointer()))
    except Exception:
        pass
    return s


def staged_detect_with_dedup(
    context,
    roi: ROI,
    *,
    N_total: int,
    stages: List[float] | None = None,
) -> Dict[str, Any]:
    """Mehrstufiges Seeding mit Dedup.
    N_total: Zielgesamt pro ROI (wird in 5 Stufen aufgeteilt). Szene-Defaults werden berücksichtigt.
    """
    if stages is None:
        stages = [1.0, 0.1, 0.01, 0.001, 0.0001]

    scn = bpy.context.scene if bpy is not None else None
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        try:
            for c in bpy.data.movieclips:
                clip = c
                break
        except Exception:
            clip = None
    if not clip:
        return {"status": "NO_CLIP"}

    current_frame = int(getattr(context.scene, "frame_current", 0)) if bpy is not None else 0

    # Baseline: alle bestehenden Marker @frame (vor Seeding)
    base_ptrs = _get_tracks_ptrs_with_marker_on_frame(clip, current_frame)

    # Zielbänder aus Szene oder berechnen
    per_stage = max(1, int(N_total // 5)) if N_total > 0 else int(scn.get("marker_stage_target", 0)) if scn else 0
    lo = int(scn.get("marker_stage_lo", int(per_stage * 0.9))) if scn else int(per_stage * 0.9)
    hi = int(scn.get("marker_stage_hi", int(per_stage * 1.1))) if scn else int(per_stage * 1.1)

    accepted_ptrs: Set[int] = set()
    results: List[Dict[str, Any]] = []

    # Stage-Loop
    for i, thr in enumerate(stages):
        # Early-Stop: optional – hier nur durchlaufen
        # Pattern/alpha je Stufe
        base_p = int(roi.pattern or 15)
        if i == 0:
            p = LIMITS.clamp_pattern(base_p - 4)
            a = LIMITS.clamp_alpha(2)
        elif i == 1:
            p = LIMITS.clamp_pattern(base_p)
            a = LIMITS.clamp_alpha(3)
        elif i == 2:
            p = LIMITS.clamp_pattern(base_p + 4)
            a = LIMITS.clamp_alpha(3)
        elif i == 3:
            p = LIMITS.clamp_pattern(base_p + 8)
            a = LIMITS.clamp_alpha(4)
        else:
            p = LIMITS.clamp_pattern(min(base_p + 12, LIMITS.pattern_max))
            a = LIMITS.clamp_alpha(4)

        search = int(_round_even(a * p))
        min_dist = int(max(2 * p, min(3.5 * p, 3 * p)))

        # Detect mit Schwellenwert thr
        detect_res = detect_mod.run_detect_basic(
            bpy.context,
            threshold=float(thr),
            margin=int(search),
            min_distance=int(min_dist),
            placement="FRAME",
            select=True,
        )

        # Dedup gegen Baseline + bereits akzeptierte
        union = set(base_ptrs) | set(accepted_ptrs)
        dist_res = dist_mod.run_distance_cleanup(
            context,
            baseline_ptrs=union,
            frame=current_frame,
            min_distance=float(min_dist),
            require_selected_new=True,
            include_muted_old=False,
            select_remaining_new=True,
            verbose=False,
            keep_zero_distance_duplicates=True,
        )

        # Neue Tracks (die nach Cleanup noch selektiert sind) einsammeln
        new_ptrs_after = _get_tracks_ptrs_with_marker_on_frame(clip, current_frame)
        created = [p for p in new_ptrs_after if p not in union]

        # Anzahlsteuerung: wenn > hi, später trimmen; wenn < lo, nächster Stage-Move
        accepted_ptrs.update(created)

        results.append({
            "stage": i,
            "threshold": thr,
            "pattern": p,
            "alpha": a,
            "search": search,
            "min_distance": min_dist,
            "detect": detect_res,
            "distance_cleanup": dist_res,
            "accepted_total": len(accepted_ptrs),
        })

        # Simple Early-Stop: wenn accepted >= per_stage, Stage beenden
        if per_stage and len(accepted_ptrs) >= per_stage:
            break

    return {
        "status": "READY",
        "stages": results,
        "accepted_total": len(accepted_ptrs),
        "per_stage_target": int(per_stage),
        "band": (int(lo), int(hi)),
    }
