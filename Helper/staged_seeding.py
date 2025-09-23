# /5-Stufen-Setzung inkl. Dedup & Mengensteuerung
from __future__ import annotations
from typing import Dict, List
import time

from .dedup import build_index, keep_if_far_enough, feedback_min_distance
from .micro_validate import validate_markers, trim_to_band


def _detect_candidates_placeholder(roi_id, threshold: float, levels: int, max_features: int, nms_window_px: int, channel: str | None = None) -> List[dict]:
    """Platzhalter für echte Detektion. Liefert aktuell keine Kandidaten.
    Struktur je Kandidat (Beispiel): {'x': float, 'y': float, 'score': float}
    """
    # TODO: hier echten Detector einhängen
    return []


def staged_detect_with_dedup(roi_id, pattern: int, alpha: int, total_target: int, scene) -> dict:
    """
    Implementiert 5 Stufen (thr: 1.0→0.0001) mit:
      - Dedup gegen Alt+Acc (min_distance aus feedback)
      - per_stage=scene['marker_stage_target'] ±10% (lo/hi)
      - Micro-Validation (10f)
      - trim/refill nach Band
    Return Summary {placed, stages, time_ms}.
    """
    t0 = time.time()

    per_stage = max(0, int(total_target // 5))
    lo = int(scene.get("marker_stage_lo", round(per_stage * 0.9))) if isinstance(scene, dict) else int(round(per_stage * 0.9))
    hi = int(scene.get("marker_stage_hi", round(per_stage * 1.1))) if isinstance(scene, dict) else int(round(per_stage * 1.1))

    profile = (scene or {}).get("detect_profile", {}) if isinstance(scene, dict) else {}
    thr_stages = [1.0, 0.1, 0.01, 0.001, 0.0001]

    min_dist = float(profile.get("min_distance_factor", 2.5)) * float(pattern)
    nms_win = int(round(float(profile.get("nms_window_factor", 1.0)) * float(pattern)))
    levels = int(profile.get("levels", 1))
    max_features = int(profile.get("max_features", 500))

    accepted: List[dict] = []
    existing = list((scene or {}).get("existing_markers", [])) if isinstance(scene, dict) else []
    index = build_index(existing)
    stages_info: List[Dict] = []

    for i, thr in enumerate(thr_stages, start=1):
        placed_this = 0
        cands = _detect_candidates_placeholder(
            roi_id=roi_id,
            threshold=thr,
            levels=levels,
            max_features=max_features,
            nms_window_px=nms_win,
            channel=(scene or {}).get("channel") if isinstance(scene, dict) else None,
        )

        kept = []
        for c in cands:
            if keep_if_far_enough(c, index, min_dist):
                kept.append(c)
                accepted.append(c)
                index["points"].append((float(c.get("x", 0.0)), float(c.get("y", 0.0))))
                placed_this += 1
                if placed_this >= hi:
                    break

        min_dist = feedback_min_distance(min_dist, placed_this, per_stage, pattern)
        kept = validate_markers(kept, frames=10, corr_min=0.60, jump_guard=True)
        if len(kept) > hi:
            kept = trim_to_band(kept, hi)

        stages_info.append({
            "stage": i,
            "threshold": thr,
            "attempted": len(cands),
            "kept": len(kept),
            "placed": placed_this,
            "min_distance_px": float(min_dist),
        })

        if placed_this >= lo:
            pass

        if isinstance(scene, dict) and scene.get("time_budget_hit", False):
            break

    summary = {
        "placed": len(accepted),
        "stages": stages_info,
        "time_ms": int(round((time.time() - t0) * 1000.0)),
    }
    return summary