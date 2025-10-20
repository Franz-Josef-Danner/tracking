# Operator/auto_calibrate_operator.py

import bpy
from typing import Iterable, List, Set, Optional, Tuple, Dict, Any
from dataclasses import dataclass  # ← NEU

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names
from ..Helper.playhead_helper import get_start_frame, reset_to_frame

SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"

# ---- NEW: Persistenz-Schlüssel für Deep-Tests ------------------------------
SCENE_DEEPTEST_ROT_XY_BEST        = "kaiserlich_deeptest_rot_xy_best"
SCENE_DEEPTEST_SCALE_BEST         = "kaiserlich_deeptest_scale_best"
SCENE_DEEPTEST_ROT_SCALE_BEST     = "kaiserlich_deeptest_rot_scale_best"
SCENE_DEEPTEST_PERSPECTIVE_BEST   = "kaiserlich_deeptest_perspective_best"

# =============================================================================
#  Utility (bestehend)
# =============================================================================

def set_all_thresholds_to_one(context: bpy.types.Context) -> None:
    scene = context.scene
    props: Iterable[str] = (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    )
    for p in props:
        if hasattr(scene, p):
            try:
                setattr(scene, p, 1.0)
            except Exception:
                pass  # fail-soft


def _call_get_start_frame(context=None):
    try:
        return get_start_frame(context) if context is not None else get_start_frame()
    except TypeError:
        return get_start_frame()


def _call_reset_to_frame(frame, context=None):
    try:
        return reset_to_frame(context, frame) if context is not None else reset_to_frame(frame)
    except TypeError:
        return reset_to_frame(frame)


def _get_active_clip(context: Optional[bpy.types.Context]) -> Optional[bpy.types.MovieClip]:
    try:
        if context and getattr(context, "space_data", None):
            clip = getattr(context.space_data, "clip", None)
            if clip:
                return clip
    except Exception:
        pass
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _list_track_names_from_clip(clip: Optional[bpy.types.MovieClip]):
    if not clip:
        return []
    try:
        return [t.name for t in clip.tracking.tracks]
    except Exception:
        return []


def _get_current_track_names(context: Optional[bpy.types.Context]) -> Set[str]:
    clip = _get_active_clip(context)
    return set(_list_track_names_from_clip(clip))


def _set_scene_props(scene: bpy.types.Scene, **kwargs) -> None:
    """Best-effort Setter für Scene-Properties (float-cast, fail-soft)."""
    for k, v in kwargs.items():
        try:
            if hasattr(scene, k):
                setattr(scene, k, float(v))
        except Exception:
            pass  # fail-soft


def short_test_track(context=None, tracks_to_delete=None):
    """
    Reihenfolge:
      1) snapshot_active_markers
      2) bpy.ops.kaiserlich_tracker.detect_adapt
      2.5) get_start_frame
      3) bpy.ops.kaiserlich_tracker.track_cycle
      4) delete_tracks_by_names (explizit/optional)
      5) reset_to_frame(start)
      6) delete newly created tracks (Delta)
      7) FINAL: get_total_track_length (nur zurückgeben, keine globale Szene-Length mehr)
    Returns:
      dict: {"total_track_length": float, "deleted_explicit": [str], "deleted_new": [str], "start_frame": int|None}
    """
    start_frame = None
    deleted_explicit: List[str] = []
    deleted_new: List[str] = []
    final_total_len: float = 0.0

    pre_names: Set[str] = _get_current_track_names(context)

    try:
        # 1) Snapshot
        try:
            (snapshot_active_markers(context) if context is not None else snapshot_active_markers())
        except TypeError:
            snapshot_active_markers()

        # 2) Detect-Adapt
        result = bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Detect-Adapt wurde abgebrochen.")

        # 2.5) Start-Frame
        start_frame = _call_get_start_frame(context)

        # 3) Track Cycle
        result = bpy.ops.kaiserlich_tracker.track_cycle('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Tracking Cycle wurde abgebrochen.")

        # 4) Optional: explizit angegebene Tracks löschen
        if tracks_to_delete:
            names = [n.strip() for n in tracks_to_delete if n and n.strip()]
            if names:
                try:
                    (delete_tracks_by_names(context, names) if context is not None else delete_tracks_by_names(names))
                except TypeError:
                    delete_tracks_by_names(names)
                deleted_explicit = names

    finally:
        # 5) Playhead zurücksetzen (best effort)
        if start_frame is not None:
            try:
                _call_reset_to_frame(start_frame, context)
            except Exception:
                pass

        # 6) FINAL: Gesamtlänge (VOR Delta-Cleanup) bestimmen
        try:
            if context is not None:
                try:
                    final_total_len = float(get_total_track_length(context))
                except TypeError:
                    final_total_len = float(get_total_track_length())
            else:
                final_total_len = float(get_total_track_length())
        except Exception:
            final_total_len = 0.0  # fail-soft

        # 7) NEU: neu erzeugte Tracks löschen (Delta)
        try:
            post_names: Set[str] = _get_current_track_names(context)
            new_names = sorted(list(post_names - pre_names))
            if new_names:
                try:
                    (delete_tracks_by_names(context, new_names) if context is not None
                     else delete_tracks_by_names(new_names))
                except TypeError:
                    delete_tracks_by_names(new_names)
                deleted_new = new_names
        except Exception:
            pass

    return {
        "total_track_length": final_total_len,   # Wert VOR Cleanup
        "deleted_explicit": deleted_explicit,
        "deleted_new": deleted_new,
        "start_frame": start_frame,
    }


def short_test_pipeline(context=None, tracks_to_delete=None):
    """
    Fährt 5 Tests in einem Run. Test 1 ist die Baseline.
    Persistiert STEP-Werte in Scene (inkl. BASE).

    Steps:
      BASE) alle relevanten Thresholds = 1.0                              -> short_test_track -> Scene[SCENE_TOTAL_TRACK_LEN_BASE]
      1)    rot_thresh_x=0, rot_thresh_y=0                                -> Scene[SCENE_TOTAL_TRACK_LEN_STEP1]
      2)    rot_thresh_x=1, rot_thresh_y=1, scale_min=0, scale_max=0      -> Scene[SCENE_TOTAL_TRACK_LEN_STEP2]
      3)    scale_min=1, scale_max=1, rot_scale_rot=0, rot_scale_scale=0  -> Scene[SCENE_TOTAL_TRACK_LEN_STEP3]
      4)    rot_scale_rot=1, rot_scale_scale=1, perspective_thresh=0      -> Scene[SCENE_TOTAL_TRACK_LEN_STEP4]
    """
    scene = (context.scene if context is not None else bpy.context.scene)
    results = {"baseline": 0, "step1": 0, "step2": 0, "step3": 0, "step4": 0}

    # --- BASELINE (alle = 1.0) ---
    try:
        _set_scene_props(scene,
            kaiserlich_rot_thresh_x=1.0,
            kaiserlich_rot_thresh_y=1.0,
            kaiserlich_scale_thresh_min=1.0,
            kaiserlich_scale_thresh_max=1.0,
            kaiserlich_rot_scale_thresh_rot=1.0,
            kaiserlich_rot_scale_thresh_scale=1.0,
            kaiserlich_perspective_thresh=1.0,
        )
        rb = short_test_track(context=context, tracks_to_delete=tracks_to_delete)
        results["baseline"] = int(float(rb.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_BASE] = results["baseline"]
        except Exception:
            pass
    except Exception:
        pass

    # --- STEP 1 ---
    try:
        _set_scene_props(scene, kaiserlich_rot_thresh_x=0.0, kaiserlich_rot_thresh_y=0.0)
        r1 = short_test_track(context=context)
        results["step1"] = int(float(r1.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_STEP1] = results["step1"]
        except Exception:
            pass
    except Exception:
        pass

    # --- STEP 2 ---
    try:
        _set_scene_props(scene,
            kaiserlich_rot_thresh_x=1.0,
            kaiserlich_rot_thresh_y=1.0,
            kaiserlich_scale_thresh_min=0.0,
            kaiserlich_scale_thresh_max=0.0,
        )
        r2 = short_test_track(context=context)
        results["step2"] = int(float(r2.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_STEP2] = results["step2"]
        except Exception:
            pass
    except Exception:
        pass

    # --- STEP 3 ---
    try:
        _set_scene_props(scene,
            kaiserlich_scale_thresh_min=1.0,
            kaiserlich_scale_thresh_max=1.0,
            kaiserlich_rot_scale_thresh_rot=0.0,
            kaiserlich_rot_scale_thresh_scale=0.0,
        )
        r3 = short_test_track(context=context)
        results["step3"] = int(float(r3.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_STEP3] = results["step3"]
        except Exception:
            pass
    except Exception:
        pass

    # --- STEP 4 ---
    try:
        _set_scene_props(scene,
            kaiserlich_rot_scale_thresh_rot=1.0,
            kaiserlich_rot_scale_thresh_scale=1.0,
            kaiserlich_perspective_thresh=0.0,
        )
        r4 = short_test_track(context=context)
        results["step4"] = int(float(r4.get("total_track_length", 0.0)))
        try:
            scene[SCENE_TOTAL_TRACK_LEN_STEP4] = results["step4"]
        except Exception:
            pass
    except Exception:
        pass

    try:
        _set_scene_props(scene, kaiserlich_perspective_thresh=1.0)
    except Exception:
        pass

    return results


def _get_scene_int(scene: bpy.types.Scene, key: str) -> Optional[int]:
    """Liest scene[key] oder scene.key und castet robust nach int. None falls nicht vorhanden."""
    try:
        if key in scene.keys():
            val = scene[key]
        elif hasattr(scene, key):
            val = getattr(scene, key)
        else:
            return None
        return int(float(val))
    except Exception:
        return None


def compare_len_steps_to_total(context=None):
    """Vergleicht STEP1..STEP4 gegen BASELINE; liefert Relations und ≥Baseline-Liste."""
    scene = (context.scene if context is not None else bpy.context.scene)
    base = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_BASE)
    v1 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP1)
    v2 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP2)
    v3 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP3)
    v4 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP4)

    values = {"STEP1": v1, "STEP2": v2, "STEP3": v3, "STEP4": v4}
    relations = {}

    def _rel(v, b):
        if v is None or b is None:
            return "missing"
        if v > b:
            return "better"
        if v == b:
            return "equal"
        return "worse"

    for k, v in values.items():
        relations[k] = _rel(v, base)

    better_or_equal = [k for k, r in relations.items() if r in ("better", "equal")]
    all_present = (base is not None) and all(v is not None for v in values.values())

    return {
        "baseline": base,
        "values": values,
        "relations": relations,
        "better_or_equal": better_or_equal,
        "all_present": all_present,
    }

# =============================================================================
#  NEW: Deep-Test – generische Helfer
# =============================================================================

def _snapshot_thresholds(scene: bpy.types.Scene) -> Dict[str, float]:
    keys = (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    )
    snap = {}
    for k in keys:
        try:
            snap[k] = float(getattr(scene, k))
        except Exception:
            pass
    return snap


def _restore_thresholds(scene: bpy.types.Scene, snap: Dict[str, float]) -> None:
    for k, v in snap.items():
        try:
            if hasattr(scene, k):
                setattr(scene, k, float(v))
        except Exception:
            pass


def _run_grid(
    context: Optional[bpy.types.Context],
    apply_params_fn,                # (scene, cfg_dict) -> None   (setzt die relevanten Thresholds)
    grid: List[Dict[str, float]],   # Liste an Konfigurationen mit expliziten Threshold-Schlüsseln
    tracks_to_delete: Optional[List[str]] = None,
    persist_best_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Führt für jede Konfiguration im Grid einen short_test_track aus.
    Rückgabe enthält alle Messungen sowie den Best-Pick.
    """
    scene = (context.scene if context is not None else bpy.context.scene)
    snap = _snapshot_thresholds(scene)

    measurements: List[Dict[str, Any]] = []
    best_len: int = -1
    best_cfg: Dict[str, float] = {}
    best_idx: int = -1

    try:
        for i, cfg in enumerate(grid):
            # Set Konfig
            try:
                apply_params_fn(scene, cfg)
            except Exception as e:
                measurements.append({
                    "index": i,
                    "params": cfg,
                    "total_track_length": 0,
                    "error": f"apply_params_failed: {e}",
                })
                continue

            # Run
            try:
                res = short_test_track(context=context, tracks_to_delete=tracks_to_delete)
                ttl = int(float(res.get("total_track_length", 0.0)))
            except Exception as e:
                ttl = 0
                res = {"error": f"short_test_failed: {e}"}

            measurements.append({
                "index": i,
                "params": cfg,
                "total_track_length": ttl,
                "meta": res,
            })

            # Best-of
            if ttl > best_len:
                best_len = ttl
                best_cfg = cfg
                best_idx = i

        # Optional persist best
        if persist_best_key and best_len >= 0:
            try:
                scene[persist_best_key] = int(best_len)
            except Exception:
                pass

    finally:
        # Restore ursprüngliche Thresholds
        _restore_thresholds(scene, snap)

    return {
        "measurements": measurements,
        "best": {
            "index": best_idx,
            "params": best_cfg,
            "total_track_length": best_len,
        }
    }

# =============================================================================
#  NEW: Deep-Test – spezialisierte Utilities
# =============================================================================

def deep_test_rot_xy(
    context: Optional[bpy.types.Context] = None,
    grid: Optional[List[Tuple[float, float]]] = None,
    tracks_to_delete: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Testet Paare für (kaiserlich_rot_thresh_x, kaiserlich_rot_thresh_y).
    Default-Grid ist konservativ.
    """
    if grid is None:
        grid = [
            (0.0, 0.0),
            (0.01, 0.01),
            (0.05, 0.05),
            (0.1, 0.1),
            (0.2, 0.2),
            (0.5, 0.5),
        ]

    def _apply(scene, cfg):
        _set_scene_props(scene,
            kaiserlich_rot_thresh_x=cfg["kaiserlich_rot_thresh_x"],
            kaiserlich_rot_thresh_y=cfg["kaiserlich_rot_thresh_y"],
        )

    grid_dicts = [{"kaiserlich_rot_thresh_x": x, "kaiserlich_rot_thresh_y": y} for (x, y) in grid]
    return _run_grid(context, _apply, grid_dicts, tracks_to_delete, SCENE_DEEPTEST_ROT_XY_BEST)


def deep_test_scale_min_max(
    context: Optional[bpy.types.Context] = None,
    grid: Optional[List[Tuple[float, float]]] = None,
    tracks_to_delete: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Testet Paare für (kaiserlich_scale_thresh_min, kaiserlich_scale_thresh_max).
    """
    if grid is None:
        grid = [
            (0.0, 0.0),
            (0.005, 0.005),
            (0.01, 0.01),
            (0.05, 0.05),
            (0.1, 0.1),
            (0.2, 0.2),
        ]

    def _apply(scene, cfg):
        _set_scene_props(scene,
            kaiserlich_scale_thresh_min=cfg["kaiserlich_scale_thresh_min"],
            kaiserlich_scale_thresh_max=cfg["kaiserlich_scale_thresh_max"],
        )

    grid_dicts = [{"kaiserlich_scale_thresh_min": mn, "kaiserlich_scale_thresh_max": mx} for (mn, mx) in grid]
    return _run_grid(context, _apply, grid_dicts, tracks_to_delete, SCENE_DEEPTEST_SCALE_BEST)


def deep_test_rot_scale_pair(
    context: Optional[bpy.types.Context] = None,
    grid: Optional[List[Tuple[float, float]]] = None,
    tracks_to_delete: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Testet Paare für (kaiserlich_rot_scale_thresh_rot, kaiserlich_rot_scale_thresh_scale).
    """
    if grid is None:
        grid = [
            (0.0, 0.0),
            (0.01, 0.01),
            (0.05, 0.05),
            (0.1, 0.1),
            (0.2, 0.2),
        ]

    def _apply(scene, cfg):
        _set_scene_props(scene,
            kaiserlich_rot_scale_thresh_rot=cfg["kaiserlich_rot_scale_thresh_rot"],
            kaiserlich_rot_scale_thresh_scale=cfg["kaiserlich_rot_scale_thresh_scale"],
        )

    grid_dicts = [{"kaiserlich_rot_scale_thresh_rot": r, "kaiserlich_rot_scale_thresh_scale": s} for (r, s) in grid]
    return _run_grid(context, _apply, grid_dicts, tracks_to_delete, SCENE_DEEPTEST_ROT_SCALE_BEST)


def deep_test_perspective(
    context: Optional[bpy.types.Context] = None,
    values: Optional[List[float]] = None,
    tracks_to_delete: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Testet Einzelwerte für (kaiserlich_perspective_thresh).
    """
    if values is None:
        values = [0.0, 0.005, 0.01, 0.02, 0.05, 0.1]

    def _apply(scene, cfg):
        _set_scene_props(scene, kaiserlich_perspective_thresh=cfg["kaiserlich_perspective_thresh"])

    grid_dicts = [{"kaiserlich_perspective_thresh": v} for v in values]
    return _run_grid(context, _apply, grid_dicts, tracks_to_delete, SCENE_DEEPTEST_PERSPECTIVE_BEST)

# =============================================================================
#  NEW: Reduction Search – generische Downward-Reduce-Algorithmen
# =============================================================================

@dataclass
class ReduceConfig:
    # Startkonfiguration
    start_single: float = 1.0
    start_pair: Tuple[float, float] = (1.0, 1.0)

    # Ziel & Grenzen
    target_len: int = 0                # Tracklänge, ab der "erfolg" gilt (≥)
    min_threshold: float = 1e-8        # Untergrenze für Threshold-Werte

    # Reduktionsfaktoren
    sf0: float = 140.0                 # initialer Reduktionsfaktor (Dein Beispiel)
    sf_halve: float = 2.0              # Halbierung pro Stufe

    # Limits
    max_outer_iters: int = 64          # max Stufen (sf-Reduktionen)
    max_inner_iters: int = 512         # max Versuche pro sf


def _is_success(measured_len: int, target_len: int) -> bool:
    return measured_len >= target_len


def reduce_threshold_single(
    context: Optional[bpy.types.Context],
    prop_name: str,
    cfg: ReduceConfig,
    tracks_to_delete: Optional[List[str]] = None,
    report_fn: Optional[Any] = None,   # ← NEU: pro Versuch loggen
) -> Dict[str, Any]:
    """
    Downward-Reduce (Single): streamt pro Kandidat nur (sf, threshold) via report_fn.
    """
    scene = (context.scene if context is not None else bpy.context.scene)
    snap = _snapshot_thresholds(scene)

    logs: List[Dict[str, float]] = []
    best_val: float = cfg.start_single
    best_len: int = -1
    best_sf: Optional[float] = None

    try:
        _set_scene_props(scene, **{prop_name: cfg.start_single})

        sf = float(cfg.sf0)
        outer = 0
        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1
            start_val = float(getattr(scene, prop_name))
            candidate = start_val / sf

            inner = 0
            while inner < cfg.max_inner_iters:
                inner += 1
                if candidate < cfg.min_threshold:
                    break

                # Log NUR sf & threshold – unmittelbar vor dem Test
                if report_fn:
                    report_fn(f"[Reduce {prop_name}] sf={sf} | threshold={candidate}")
                logs.append({"sf": sf, "threshold": candidate})

                _set_scene_props(scene, **{prop_name: candidate})
                res = short_test_track(context=context, tracks_to_delete=tracks_to_delete)
                ttl = int(float(res.get("total_track_length", 0.0)))

                if ttl >= cfg.target_len:
                    if ttl > best_len:
                        best_len = ttl
                        best_val = candidate
                        best_sf = sf
                    break
                else:
                    candidate = candidate / sf

            sf = sf / cfg.sf_halve

    finally:
        _restore_thresholds(scene, snap)

    return {
        "prop": prop_name,
        "best": {"value": best_val, "sf": best_sf},
        "log": logs,  # enthält nur (sf, threshold) je Versuch
    }


def reduce_threshold_pair(
    context: Optional[bpy.types.Context],
    prop_a: str, prop_b: str,
    cfg: ReduceConfig,
    coupling: str = "uniform",
    tracks_to_delete: Optional[List[str]] = None,
    report_fn: Optional[Any] = None,   # ← NEU
) -> Dict[str, Any]:
    """
    Downward-Reduce (Pair): streamt pro Kandidat nur (sf, (a,b)) via report_fn.
    """
    scene = (context.scene if context is not None else bpy.context.scene)
    snap = _snapshot_thresholds(scene)

    logs: List[Dict[str, Any]] = []
    best_pair: Tuple[float, float] = tuple(cfg.start_pair)
    best_len: int = -1
    best_sf: Optional[float] = None

    try:
        _set_scene_props(scene, **{prop_a: cfg.start_pair[0], prop_b: cfg.start_pair[1]})

        sf = float(cfg.sf0)
        outer = 0
        while sf >= 1.0 and outer < cfg.max_outer_iters:
            outer += 1

            a0 = float(getattr(scene, prop_a))
            b0 = float(getattr(scene, prop_b))
            cand_a = a0 / sf
            cand_b = b0 / sf

            inner = 0
            while inner < cfg.max_inner_iters:
                inner += 1
                if cand_a < cfg.min_threshold and cand_b < cfg.min_threshold:
                    break

                if report_fn:
                    report_fn(f"[Reduce {prop_a}+{prop_b}] sf={sf} | thresholds=({cand_a}, {cand_b})")
                logs.append({"sf": sf, "thresholds": (cand_a, cand_b)})

                _set_scene_props(scene, **{prop_a: cand_a, prop_b: cand_b})
                res = short_test_track(context=context, tracks_to_delete=tracks_to_delete)
                ttl = int(float(res.get("total_track_length", 0.0)))

                if ttl >= cfg.target_len:
                    if ttl > best_len:
                        best_len = ttl
                        best_pair = (cand_a, cand_b)
                        best_sf = sf
                    break
                else:
                    cand_a = cand_a / sf
                    cand_b = cand_b / sf

            sf = sf / cfg.sf_halve

    finally:
        _restore_thresholds(scene, snap)

    return {
        "props": (prop_a, prop_b),
        "best": {"values": best_pair, "sf": best_sf},
        "log": logs,  # nur (sf, (a,b)) je Versuch
    }


# ---- Bequeme Wrapper für Deine 4 Gruppen -----------------------------------

def reduce_rot_xy(context, target_len: int, start: Tuple[float, float] = (1.0, 1.0), report_fn=None, **kw):
    cfg = ReduceConfig(target_len=target_len, start_pair=start, **kw)
    return reduce_threshold_pair(context, "kaiserlich_rot_thresh_x", "kaiserlich_rot_thresh_y", cfg, report_fn=report_fn)

def reduce_scale_min_max(context, target_len: int, start: Tuple[float, float] = (1.0, 1.0), report_fn=None, **kw):
    cfg = ReduceConfig(target_len=target_len, start_pair=start, **kw)
    return reduce_threshold_pair(context, "kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max", cfg, report_fn=report_fn)

def reduce_rot_scale_pair(context, target_len: int, start: Tuple[float, float] = (1.0, 1.0), report_fn=None, **kw):
    cfg = ReduceConfig(target_len=target_len, start_pair=start, **kw)
    return reduce_threshold_pair(context, "kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale", cfg, report_fn=report_fn)

def reduce_perspective(context, target_len: int, start: float = 1.0, report_fn=None, **kw):
    cfg = ReduceConfig(target_len=target_len, start_single=start, **kw)
    return reduce_threshold_single(context, "kaiserlich_perspective_thresh", cfg, report_fn=report_fn)


# =============================================================================
#  Operator (bestehend)
# =============================================================================

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: setzt alle Ziel-Parameter auf 1.0 und führt danach Detect-Adapt & Tracking aus."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    tracks_to_delete: bpy.props.StringProperty(
        name="Tracks to delete (comma-separated)",
        default="",
        description="Optional: Namen der zu löschenden Tracks, getrennt durch Kommas"
    )

    def execute(self, context):
        try:
            set_all_thresholds_to_one(context)
            self.report({'INFO'}, "KaiserlichTracker: Thresholds => 1.0")

            # ---- 1) Short-Test-Pipeline fahren & persistieren ----
            try:
                names = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
                pipeline_results = short_test_pipeline(context=context, tracks_to_delete=names)
                bl = int(pipeline_results.get('baseline', 0))
                s1 = int(pipeline_results.get('step1', 0))
                s2 = int(pipeline_results.get('step2', 0))
                s3 = int(pipeline_results.get('step3', 0))
                s4 = int(pipeline_results.get('step4', 0))
                self.report(
                    {'INFO'},
                    (f"Short-Test-Pipeline abgeschlossen | "
                     f"Baseline={bl} | Step1={s1} Step2={s2} Step3={s3} Step4={s4}")
                )
            except Exception as e:
                self.report({'ERROR'}, f"Short-Test-Pipeline fehlgeschlagen: {e}")
                # Falls Short-Test scheitert, abbrechen – lange Tests wären ungerichtet.
                return {'CANCELLED'}

            # ---- 2) Auswertung -> entscheidet, welche langen Tests starten ----
            try:
                cmp_res = compare_len_steps_to_total(context)
                base = int(cmp_res.get("baseline") or 0)
                vals = cmp_res.get("values", {})
                rels = cmp_res.get("relations", {})
                ge_list = cmp_res.get("better_or_equal", [])

                self.report(
                    {'INFO'},
                    (f"Baseline={base} | "
                     f"STEP1={vals.get('STEP1')}({rels.get('STEP1')}) "
                     f"STEP2={vals.get('STEP2')}({rels.get('STEP2')}) "
                     f"STEP3={vals.get('STEP3')}({rels.get('STEP3')}) "
                     f"STEP4={vals.get('STEP4')}({rels.get('STEP4')})")
                )
                self.report({'INFO'}, "≥ Baseline: " + (", ".join(ge_list) if ge_list else "none"))

                # ---- 3) Lange Tests automatisch gemäß Auswertung ----
                # Target pro Step = max(Baseline, STEPn)
                scene = context.scene

                # STEP1 → Rot/XY
                if "STEP1" in ge_list:
                    target_len = max(base, int(vals.get("STEP1") or 0))
                    r = reduce_rot_xy(context, target_len=target_len,
                                      report_fn=lambda msg: self.report({'INFO'}, msg))
                    best = r.get("best", {})
                    scene[SCENE_DEEPTEST_ROT_XY_BEST] = int(target_len)
                    # kein Finalwert nötig; falls doch:
                    # self.report({'INFO'}, f"[Reduce RotXY] best sf={best.get('sf')} | thresh={best.get('values')}")
                
                # STEP2 → Scale Min/Max
                if "STEP2" in ge_list:
                    target_len = max(base, int(vals.get("STEP2") or 0))
                    r = reduce_scale_min_max(context, target_len=target_len,
                                             report_fn=lambda msg: self.report({'INFO'}, msg))
                    best = r.get("best", {})
                    scene[SCENE_DEEPTEST_SCALE_BEST] = int(target_len)
                
                # STEP3 → Rot+Scale Pair
                if "STEP3" in ge_list:
                    target_len = max(base, int(vals.get("STEP3") or 0))
                    r = reduce_rot_scale_pair(context, target_len=target_len,
                                              report_fn=lambda msg: self.report({'INFO'}, msg))
                    best = r.get("best", {})
                    scene[SCENE_DEEPTEST_ROT_SCALE_BEST] = int(target_len)
                
                # STEP4 → Perspective
                if "STEP4" in ge_list:
                    target_len = max(base, int(vals.get("STEP4") or 0))
                    r = reduce_perspective(context, target_len=target_len,
                                           report_fn=lambda msg: self.report({'INFO'}, msg))
                    best = r.get("best", {})
                    scene[SCENE_DEEPTEST_PERSPECTIVE_BEST] = int(target_len)


            except Exception as e:
                self.report({'ERROR'}, f"Auswertung/Long-Tests fehlgeschlagen: {e}")
                return {'CANCELLED'}

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Auto-Calibrate fehlgeschlagen: {e}")
            return {'CANCELLED'}



def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
