import bpy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..Helper.util_thresholds import snapshot_thresholds, restore_thresholds
from ..Helper.util_scene import set_scene_props
from ..Helper.util_shorttest import short_test_track
from ..Helper.util_hwratio import get_hw_ratio


# ---------------------------------------------------------------------------
# KONFIG & BASIS
# ---------------------------------------------------------------------------
@dataclass
class ReduceConfig:
    start_single: float = 1.0
    start_pair: Tuple[float, float] = (1.0, 1.0)
    target_len: int = 0
    min_threshold: float = 1e-8
    sf0: float = 140.0
    sf_halve: float = 2.0
    max_outer_iters: int = 64
    max_inner_iters: int = 512


def _is_success(measured_len: int, target_len: int) -> bool:
    return measured_len >= target_len


# ---------------------------------------------------------------------------
# REDUCE SINGLE
# ---------------------------------------------------------------------------
def reduce_threshold_single(context, prop_name, cfg: ReduceConfig, tracks_to_delete=None, report_fn=None):
    scene = (context.scene if context else bpy.context.scene)
    snap = snapshot_thresholds(scene)
    logs, best_val, best_len, best_sf = [], cfg.start_single, -1, None

    try:
        current_start = float(cfg.start_single)
        last_success_prev_global = None
        sf, outer = float(cfg.sf0), 0

        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1
            prev, had_success, next_start_after_stage = current_start, False, None

            for inner in range(cfg.max_inner_iters):
                cand = prev / sf
                if cand < cfg.min_threshold: break

                set_scene_props(scene, **{prop_name: cand})
                res = short_test_track(context=context, tracks_to_delete=tracks_to_delete,
                                       run_meta={"sf": sf, "fields": [prop_name]}, report_fn=report_fn)
                ttl = int(float(res.get("total_track_length", 0.0)))
                logs.append({"sf": sf, "threshold": cand})
                if _is_success(ttl, cfg.target_len):
                    if ttl > best_len: best_val, best_len, best_sf = cand, ttl, sf
                    last_success_prev_global, next_start_after_stage, had_success = prev, prev, True
                    break
                prev = cand

            current_start = next_start_after_stage or last_success_prev_global or current_start
            sf /= cfg.sf_halve

    finally:
        restore_thresholds(scene, snap)

    return {"prop": prop_name, "best": {"value": best_val, "sf": best_sf}, "log": logs}


# ---------------------------------------------------------------------------
# REDUCE SINGLE WITH FIXED EXTRAS
# ---------------------------------------------------------------------------
def reduce_threshold_single_with_extras(context, prop_name, cfg: ReduceConfig, extra_fixed: Dict[str, float],
                                        tracks_to_delete=None, report_fn=None):
    scene = (context.scene if context else bpy.context.scene)
    snap = snapshot_thresholds(scene)
    logs, best_val, best_len, best_sf = [], cfg.start_single, -1, None
    try:
        current_start, last_success_prev_global, sf, outer = float(cfg.start_single), None, float(cfg.sf0), 0
        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1
            prev, had_success, next_start_after_stage = current_start, False, None
            for inner in range(cfg.max_inner_iters):
                cand = prev / sf
                if cand < cfg.min_threshold: break
                props = {prop_name: cand, **extra_fixed}
                set_scene_props(scene, **props)
                res = short_test_track(context=context, tracks_to_delete=tracks_to_delete,
                                       run_meta={"sf": sf, "fields": list(props.keys())}, report_fn=report_fn)
                ttl = int(float(res.get("total_track_length", 0.0)))
                logs.append({"sf": sf, "threshold": cand, "extras": extra_fixed})
                if _is_success(ttl, cfg.target_len):
                    if ttl > best_len: best_val, best_len, best_sf = cand, ttl, sf
                    last_success_prev_global, next_start_after_stage,