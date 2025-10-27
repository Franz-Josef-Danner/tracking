# =============================================================================
#  util_reduce.py – Downward-Reduce-Algorithmen für Threshold-Kalibrierung
# =============================================================================

import bpy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..Helper.util_thresholds import snapshot_thresholds, restore_thresholds
from ..Helper.util_scene import set_scene_props
from ..Helper.util_hwratio import get_hw_ratio
from ..Helper.util_shorttest import short_test_track


# -----------------------------------------------------------------------------
#  Konfiguration
# -----------------------------------------------------------------------------
@dataclass
class ReduceConfig:
    """Parameter-Container für Reduktionsläufe."""
    start_single: float = 1.0
    start_pair: Tuple[float, float] = (1.0, 1.0)
    target_len: int = 0
    min_threshold: float = 1e-8
    sf0: float = 140.0
    sf_halve: float = 2.0
    max_outer_iters: int = 64
    max_inner_iters: int = 512


# -----------------------------------------------------------------------------
#  Hilfsfunktionen
# -----------------------------------------------------------------------------
def _is_success(measured_len: int, target_len: int) -> bool:
    """Gilt als Erfolg, wenn gemessene Länge ≥ Ziel-Länge."""
    return measured_len >= target_len


# -----------------------------------------------------------------------------
#  Single-Threshold-Reducer
# -----------------------------------------------------------------------------
def reduce_threshold_single(
    context: Optional[bpy.types.Context],
    prop_name: str,
    cfg: ReduceConfig,
    tracks_to_delete: Optional[List[str]] = None,
    report_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Downward-Reduce (Single):
    - cand = prev / sf
    - Bei Erfolg: Start für nächste Stufe = vorheriger Wert
    - Kein Erfolg: greift auf global letzten Erfolg zurück
    """
    scene = (context.scene if context else bpy.context.scene)
    snap = snapshot_thresholds(scene)
    logs: List[Dict[str, Any]] = []

    best_val = cfg.start_single
    best_len = -1
    best_sf = None
    current_start = float(cfg.start_single)
    last_success_prev_global = None

    try:
        sf = float(cfg.sf0)
        outer = 0
        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1
            prev = current_start
            had_success = False
            next_start_after_stage = None

            inner = 0
            while inner < cfg.max_inner_iters:
                inner += 1
                candidate = prev / sf
                if candidate < cfg.min_threshold:
                    break

                set_scene_props(scene, **{prop_name: candidate})
                res = short_test_track(
                    context=context,
                    tracks_to_delete=tracks_to_delete,
                    run_meta={"sf": sf, "fields": [prop_name], "tag": f"Reduce {prop_name}"},
                    report_fn=report_fn
                )
                ttl = int(float(res.get("total_track_length", 0.0)))
                logs.append({"sf": sf, "threshold": candidate, "len": ttl})

                if _is_success(ttl, cfg.target_len):
                    best_val, best_len, best_sf = candidate, ttl, sf
                    last_success_prev_global = prev
                    next_start_after_stage = prev
                    had_success = True
                    break
                else:
                    prev = candidate

            current_start = next_start_after_stage or last_success_prev_global or current_start
            sf /= cfg.sf_halve

    finally:
        restore_thresholds(scene, snap)

    return {"prop": prop_name, "best": {"value": best_val, "sf": best_sf}, "log": logs}


# -----------------------------------------------------------------------------
#  Single-Threshold mit festen Zusatz-Parametern
# -----------------------------------------------------------------------------
def reduce_threshold_single_with_extras(
    context: Optional[bpy.types.Context],
    prop_name: str,
    cfg: ReduceConfig,
    extra_fixed: Dict[str, float],
    tracks_to_delete: Optional[List[str]] = None,
    report_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    scene = (context.scene if context else bpy.context.scene)
    snap = snapshot_thresholds(scene)
    logs: List[Dict[str, Any]] = []

    best_val = cfg.start_single
    best_len = -1
    best_sf = None
    current_start = float(cfg.start_single)
    last_success_prev_global = None

    try:
        sf = float(cfg.sf0)
        outer = 0
        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1
            prev = current_start
            had_success = False
            next_start_after_stage = None

            inner = 0
            while inner < cfg.max_inner_iters:
                inner += 1
                candidate = prev / sf
                if candidate < cfg.min_threshold:
                    break

                props = {prop_name: candidate}
                props.update({k: float(v) for k, v in (extra_fixed or {}).items()})
                set_scene_props(scene, **props)

                fields = [prop_name] + list((extra_fixed or {}).keys())
                res = short_test_track(
                    context=context,
                    tracks_to_delete=tracks_to_delete,
                    run_meta={"sf": sf, "fields": fields, "tag": f"Reduce {prop_name} (+extras)"},
                    report_fn=report_fn
                )
                ttl = int(float(res.get("total_track_length", 0.0)))
                logs.append({"sf": sf, "threshold": candidate, "extras": extra_fixed, "len": ttl})

                if _is_success(ttl, cfg.target_len):
                    best_val, best_len, best_sf = candidate, ttl, sf
                    last_success_prev_global = prev
                    next_start_after_stage = prev
                    had_success = True
                    break
                else:
                    prev = candidate

            current_start = next_start_after_stage or last_success_prev_global or current_start
            sf /= cfg.sf_halve

    finally:
        restore_thresholds(scene, snap)

    return {
        "prop": prop_name,
        "best": {"value": best_val, "sf": best_sf},
        "log": logs,
        "extras": dict(extra_fixed or {}),
    }


# -----------------------------------------------------------------------------
#  Pair-Reducer
# -----------------------------------------------------------------------------
def reduce_threshold_pair(
    context: Optional[bpy.types.Context],
    prop_a: str,
    prop_b: str,
    cfg: ReduceConfig,
    coupling: str = "uniform",
    tracks_to_delete: Optional[List[str]] = None,
    report_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    scene = (context.scene if context else bpy.context.scene)
    snap = snapshot_thresholds(scene)
    logs: List[Dict[str, Any]] = []

    best_pair = tuple(cfg.start_pair)
    best_len = -1
    best_sf = None

    current_start_a, current_start_b = map(float, cfg.start_pair)
    last_success_prev_global = None

    try:
        sf = float(cfg.sf0)
        outer = 0
        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1
            prev_a, prev_b = current_start_a, current_start_b
            had_success = False
            next_start_after_stage = None

            inner = 0
            while inner < cfg.max_inner_iters:
                inner += 1
                cand_a, cand_b = prev_a / sf, prev_b / sf
                if cand_a < cfg.min_threshold and cand_b < cfg.min_threshold:
                    break

                set_scene_props(scene, **{prop_a: cand_a, prop_b: cand_b})
                res = short_test_track(
                    context=context,
                    tracks_to_delete=tracks_to_delete,
                    run_meta={"sf": sf, "fields": [prop_a, prop_b], "tag": f"Reduce {prop_a}+{prop_b}"},
                    report_fn=report_fn
                )
                ttl = int(float(res.get("total_track_length", 0.0)))
                logs.append({"sf": sf, "thresholds": (cand_a, cand_b), "len": ttl})

                if _is_success(ttl, cfg.target_len):
                    best_pair, best_len, best_sf = (cand_a, cand_b), ttl, sf
                    last_success_prev_global = (prev_a, prev_b)
                    next_start_after_stage = (prev_a, prev_b)
                    had_success = True
                    break
                else:
                    prev_a, prev_b = cand_a, cand_b

            if had_success:
                current_start_a, current_start_b = next_start_after_stage
            elif last_success_prev_global:
                current_start_a, current_start_b = last_success_prev_global

            sf /= cfg.sf_halve

    finally:
        restore_thresholds(scene, snap)

    return {"props": (prop_a, prop_b), "best": {"values": best_pair, "sf": best_sf}, "log": logs}


# -----------------------------------------------------------------------------
#  Gekoppelte Varianten (Rot-XY und Scale-Min/Max)
# -----------------------------------------------------------------------------
def reduce_threshold_rot_xy_coupled(
    context: Optional[bpy.types.Context],
    prop_x: str,
    prop_y: str,
    hw_ratio: float,
    cfg: ReduceConfig,
    tracks_to_delete: Optional[List[str]] = None,
    report_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Nur prop_x reduzieren; prop_y = prop_x * hw_ratio."""
    scene = (context.scene if context else bpy.context.scene)
    snap = snapshot_thresholds(scene)
    logs: List[Dict[str, Any]] = []

    best_x = cfg.start_single
    best_y = cfg.start_single * hw_ratio
    best_len = -1
    best_sf = None
    current_start_x = float(cfg.start_single)
    last_success_prev_global = None

    try:
        sf = float(cfg.sf0)
        outer = 0
        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1
            prev_x = current_start_x
            had_success = False
            next_start_after_stage = None
            inner = 0
            while inner < cfg.max_inner_iters:
                inner += 1
                cand_x = prev_x / sf
                if cand_x < cfg.min_threshold:
                    break
                cand_y = cand_x * hw_ratio
                set_scene_props(scene, **{prop_x: cand_x, prop_y: cand_y})
                res = short_test_track(
                    context=context,
                    tracks_to_delete=tracks_to_delete,
                    run_meta={"sf": sf, "fields": [prop_x, prop_y], "tag": f"Reduce {prop_x}(Y coupled)"},
                    report_fn=report_fn
                )
                ttl = int(float(res.get("total_track_length", 0.0)))
                logs.append({"sf": sf, "thresholds": (cand_x, cand_y), "ratio": hw_ratio, "len": ttl})
                if _is_success(ttl, cfg.target_len):
                    best_x, best_y, best_len, best_sf = cand_x, cand_y, ttl, sf
                    last_success_prev_global = prev_x
                    next_start_after_stage = prev_x
                    had_success = True
                    break
                else:
                    prev_x = cand_x
            current_start_x = next_start_after_stage or last_success_prev_global or current_start_x
            sf /= cfg.sf_halve
    finally:
        restore_thresholds(scene, snap)

    return {"props": (prop_x, prop_y), "best": {"values": (best_x, best_y), "sf": best_sf, "ratio": hw_ratio}, "log": logs}


def reduce_threshold_scale_coupled(
    context: Optional[bpy.types.Context],
    prop_min: str,
    prop_max: str,
    factor: float,
    cfg: ReduceConfig,
    tracks_to_delete: Optional[List[str]] = None,
    report_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Nur prop_min reduzieren; prop_max = prop_min * factor."""
    scene = (context.scene if context else bpy.context.scene)
    snap = snapshot_thresholds(scene)
    logs: List[Dict[str, Any]] = []

    best_min = cfg.start_single
    best_max = cfg.start_single * factor
    best_len = -1
    best_sf = None
    current_start_min = float(cfg.start_single)
    last_success_prev_global = None

    try:
        sf = float(cfg.sf0)
        outer = 0
        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1
            prev_min = current_start_min
            had_success = False
            next_start_after_stage = None
            inner = 0
            while inner < cfg.max_inner_iters:
                inner += 1
                cand_min = prev_min / sf
                if cand_min < cfg.min_threshold:
                    break
                cand_max = cand_min * factor
                set_scene_props(scene, **{prop_min: cand_min, prop_max: cand_max})
                res = short_test_track(
                    context=context,
                    tracks_to_delete=tracks_to_delete,
                    run_meta={"sf": sf, "fields": [prop_min, prop_max], "tag": f"Reduce {prop_min}(Max coupled)"},
                    report_fn=report_fn
                )
                ttl = int(float(res.get("total_track_length", 0.0)))
                logs.append({"sf": sf, "thresholds": (cand_min, cand_max), "factor": factor, "len": ttl})
                if _is_success(ttl, cfg.target_len):
                    best_min, best_max, best_len, best_sf = cand_min, cand_max, ttl, sf
                    last_success_prev_global = prev_min
                    next_start_after_stage = prev_min
                    had_success = True
                    break
                else:
                    prev_min = cand_min
            current_start_min = next_start_after_stage or last_success_prev_global or current_start_min
            sf /= cfg.sf_halve
    finally:
        restore_thresholds(scene, snap)

    return {"props": (prop_min, prop_max), "best": {"values": (best_min, best_max), "sf": best_sf, "factor": factor}, "log": logs}


# -----------------------------------------------------------------------------
#  Wrapper-Funktionen für Hauptgruppen
# -----------------------------------------------------------------------------
def reduce_rot_xy(context, target_len: int, start: Tuple[float, float] = (1.0, 1.0), report_fn=None, **kw):
    """Rot-XY-Haupttest (X reduziert, Y = X * Ratio)."""
    ratio = get_hw_ratio(context)
    cfg = ReduceConfig(target_len=target_len, start_single=float(start[0]), **kw)
    return reduce_threshold_rot_xy_coupled(context, "kaiserlich_rot_thresh_x", "kaiserlich_rot_thresh_y", ratio, cfg, report_fn=report_fn)


def reduce_scale_min_max(context, target_len: int, start: Tuple[float, float] = (1.0, 1.0), report_fn=None, **kw):
    """Scale-Min/Max-Haupttest (Min reduziert, Max = Min * 1.1)."""
    factor = 1.1
    cfg = ReduceConfig(target_len=target_len, start_single=float(start[0]), **kw)
    return reduce_threshold_scale_coupled(context, "kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max", factor, cfg, report_fn=report_fn)


def reduce_rot_scale_pair(context, target_len: int, start: Tuple[float, float] = (1.0, 1.0), report_fn=None, **kw):
    """Zweistufig: erst rot (scale=0), dann scale (rot=0)."""
    cfg_rot = ReduceConfig(target_len=int(target_len or 0), start_single=float(start[0]), **kw)
    res_rot = reduce_threshold_single_with_extras(
        context=context,
        prop_name="kaiserlich_rot_scale_thresh_rot",
        cfg=cfg_rot,
        extra_fixed={"kaiserlich_rot_scale_thresh_scale": 0.0},
        report_fn=report_fn,
    )
    best_rot = float(res_rot.get("best", {}).get("value", start[0]))

    cfg_scale = ReduceConfig(target_len=int(target_len or 0), start_single=float(start[1]), **kw)
    res_scale = reduce_threshold_single_with_extras(
        context=context,
        prop_name="kaiserlich_rot_scale_thresh_scale",
        cfg=cfg_scale,
        extra_fixed={"kaiserlich_rot_scale_thresh_rot": 0.0},
        report_fn=report_fn,
    )
    best_scale = float(res_scale.get("best", {}).get("value", start[1]))
    sf_scale = res_scale.get("best", {}).get("sf")

    return {
        "props": ("kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale"),
        "best": {"values": (best_rot, best_scale), "sf": sf_scale},
        "log": {"rot": res_rot.get("log", []), "scale": res_scale.get("log", [])},
    }


def reduce_perspective(context, target_len: int, start: float = 1.0, report_fn=None, **kw):
    """Reduktion für Perspective-Threshold."""
    cfg = ReduceConfig(target_len=target_len, start_single=start, **kw)
    return reduce_threshold_single(context, "kaiserlich_perspective_thresh", cfg, report_fn=report_fn)
