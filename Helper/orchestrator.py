# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/orchestrator.py – Kompakter Ablauf (Orchestrator)

STRM analysieren → ROIs priorisieren
Startwerte setzen (pattern/search, Channel)
Detect autotunen → staged seeding mit Dedup + /5-Zielband + Micro-Validation
Frame-Loop: track-1-step → eval → α-Adjust (apply next), ggf. gated pattern-update
Alle 20–40 Frames/Cluster: Model-Fit & Selection (mit Strafe/Hysterese)
Peer-Snap/Refresh, Reseeding in Löchern, periodische Cleanup-Passes
KPIs aggregieren, Presets aktualisieren, Summary reporten

Schnittstellen (Helper-API)
- ROI/STRM: analyze_rois()
- Init: init_pattern_search(roi), select_channel(roi)
- Detect: autotune_detect(roi), staged_detect_with_dedup(roi, pattern, alpha, N_total)
- Online: track_one_frame(roi), schedule_param_changes(roi, telem)
- Models: cluster_fit_models(roi, window), select_apply_motion_models(roi, fits, feats)
- Stabilisierung: peer_snap_and_refresh(roi), reseed_coverage_holes(roi), periodic_cleanup(roi)
- Persistence: finalize_metrics(), write_presets()
"""
from __future__ import annotations

from typing import List, Dict, Any, Tuple
import time

from .strm import analyze_rois, ROI
from .init_params import init_pattern_search, select_channel
from .autotune import autotune_detect
from .seeding import staged_detect_with_dedup
from .online_adapt import track_one_frame
from .models_select import cluster_fit_models, select_apply_motion_models
from .stabilization import peer_snap_and_refresh, reseed_coverage_holes, periodic_cleanup
from .governance import KPI, TimeBudget, seed_rng
from .persistence import finalize_metrics, write_presets

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover
    bpy = None  # type: ignore

__all__ = ("run_full_cycle",)


def _scene_int(scn, key: str, default: int) -> int:
    try:
        return int(scn.get(key, default))
    except Exception:
        return int(default)


def _scene_float(scn, key: str, default: float) -> float:
    try:
        return float(scn.get(key, default))
    except Exception:
        return float(default)


def run_full_cycle(context, *, tiles: Tuple[int, int] = (4, 6), markers_total: int = 250) -> Dict[str, Any]:
    scn = bpy.context.scene if bpy is not None else None

    # Governance/Seeds aus Scene-Keys
    trial_ns = str((scn.get("kc_trial_ns") if scn else "Trial")).strip() or "Trial"
    sample_frames = _scene_int(scn, "kc_sample_frames", 5) if scn else 5
    tiles_y = _scene_int(scn, "kc_tiles_y", tiles[0]) if scn else int(tiles[0])
    tiles_x = _scene_int(scn, "kc_tiles_x", tiles[1]) if scn else int(tiles[1])

    # Zeitbudget (Sekunden) – Default: 0.25 s/ROI, 0.05 s/Stage
    tb_total = _scene_float(scn, "kc_budget_roi_sec", 0.25) if scn else 0.25
    tb_stage = _scene_float(scn, "kc_budget_stage_sec", 0.05) if scn else 0.05

    if scn is not None:
        scn["kc_runtime_cfg"] = {
            "trial_ns": trial_ns,
            "sample_frames": int(sample_frames),
            "tiles": [int(tiles_y), int(tiles_x)],
            "budget": {"roi_sec": float(tb_total), "stage_sec": float(tb_stage)},
        }

    # STRM/ROIs
    rois: List[ROI] = analyze_rois(context, tiles_y=int(tiles_y), tiles_x=int(tiles_x), sample_frames=int(sample_frames))

    # Heuristische Priorisierung: höchste Textur zuerst
    rois.sort(key=lambda r: (-r.tau_tex, r.v_motion))

    cycle_results: List[Dict[str, Any]] = []
    t_cycle0 = time.perf_counter()

    for roi in rois:
        # Seed pro ROI für deterministische Micro-Trials
        cur_frame = int(getattr(context.scene, "frame_current", 0)) if bpy is not None else 0
        seed_rng(trial_ns, roi.id, stage=0, frame=cur_frame)

        # Zeitbudget für ROI starten
        tbudget = TimeBudget(seconds_total=float(tb_total), seconds_stage=float(tb_stage))
        tbudget.start()

        roi = init_pattern_search(context, roi)
        roi = select_channel(context, roi)

        # Detect/Seeding – Early Stop, wenn Budget erschöpft
        _ = autotune_detect(context, roi)

        # Staged seeding mit Budget-Kontrolle: Abbruch, wenn ROI-Budget erschöpft
        seed_res = staged_detect_with_dedup(context, roi, N_total=int(markers_total // max(1, len(rois))))
        tbudget.stop_and_accumulate()
        if tbudget.remaining_total() <= 0.0:
            cycle_results.append({
                "roi": roi.id,
                "pattern": roi.pattern,
                "alpha": roi.alpha,
                "seed": seed_res,
                "budget_exhausted": True,
            })
            # Skip Rest (Online/Models/Cleanup), nächster ROI
            continue

        # Online (ein Schritt als Demo)
        telem = {"corr": 0.93, "fail": False}
        online = track_one_frame(context, roi, telem)

        # Models (alle 30f; hier direkt)
        fits = cluster_fit_models(context, roi, window=30)
        model_res = select_apply_motion_models(context, roi, fits, feats=None)

        # Stabilisierung/Cleanup
        _ = peer_snap_and_refresh(context, roi)
        _ = reseed_coverage_holes(context, roi)
        cleanup_res = periodic_cleanup(context, roi)

        # KPIs sammeln (Platzhalter) und persistieren
        kpi = KPI(survival10=0.8, survival30=0.7, corr_median=0.9, residual_rms=0.7, coverage_tiles=0.6, redundancy_index=0.5, time_per_frame_ms=20)
        score_res = finalize_metrics(context, roi, kpi)
        _ = write_presets(context, roi, kpi, detect_threshold=float(seed_res.get("stages", [{}])[-1].get("threshold", 0.5) if seed_res.get("stages") else 0.5))

        cycle_results.append({
            "roi": roi.id,
            "pattern": roi.pattern,
            "alpha": roi.alpha,
            "seed": seed_res,
            "online": online,
            "model": model_res,
            "cleanup": cleanup_res,
            "score": score_res,
        })

    total_ms = (time.perf_counter() - t_cycle0) * 1000.0
    return {"status": "READY", "rois": len(rois), "time_ms": float(total_ms), "results": cycle_results}
