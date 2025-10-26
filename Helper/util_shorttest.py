import bpy
from typing import Any, Dict, List, Optional, Set

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names
from ..Helper.util_clip import get_current_track_names
from ..Helper.util_scene import call_get_start_frame, call_reset_to_frame, set_scene_props
from ..Helper.util_format import fmt8


# ---- Scene-Key-Konstanten ----------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"


# =============================================================================
# Short-Test
# =============================================================================

def short_test_track(
    context=None,
    tracks_to_delete=None,
    run_meta: Optional[Dict[str, Any]] = None,
    report_fn: Optional[Any] = None
) -> Dict[str, Any]:
    """Führt einen Einzeldurchlauf der Tracking-Pipeline mit Live-Log durch."""
    start_frame = None
    deleted_explicit: List[str] = []
    deleted_new: List[str] = []
    final_total_len: float = 0.0

    scene = (context.scene if context else bpy.context.scene)
    if run_meta is None:
        run_meta = {}

    # --- Live-Log der Thresholds ---
    fields: List[str] = run_meta.get("fields") or [
        "kaiserlich_rot_thresh_x", "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]
    tag: str = run_meta.get("tag") or "TEST"
    sf = run_meta.get("sf", None)

    kv = []
    for f in fields:
        try:
            v = float(getattr(scene, f))
            kv.append(f"{f}={fmt8(v)}")
        except Exception:
            pass
    if sf is not None:
        kv.insert(0, f"sf={fmt8(sf)}")
    if report_fn and kv:
        report_fn(f"[{tag}] " + " | ".join(kv))

    pre_names: Set[str] = get_current_track_names(context)

    try:
        snapshot_active_markers(context)
        if 'CANCELLED' in bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT'):
            raise RuntimeError("Detect-Adapt abgebrochen")

        start_frame = call_get_start_frame(context)

        if 'CANCELLED' in bpy.ops.kaiserlich_tracker.track_cycle('EXEC_DEFAULT'):
            raise RuntimeError("Track-Cycle abgebrochen")

        if tracks_to_delete:
            names = [n.strip() for n in tracks_to_delete if n and n.strip()]
            delete_tracks_by_names(context, names)
            deleted_explicit = names

    finally:
        if start_frame is not None:
            call_reset_to_frame(start_frame, context)

        try:
            final_total_len = float(get_total_track_length(context))
        except Exception:
            final_total_len = 0.0

        try:
            post_names = get_current_track_names(context)
            new_names = sorted(list(post_names - pre_names))
            if new_names:
                delete_tracks_by_names(context, new_names)
                deleted_new = new_names
        except Exception:
            pass

    return {
        "total_track_length": final_total_len,
        "deleted_explicit": deleted_explicit,
        "deleted_new": deleted_new,
        "start_frame": start_frame,
    }


# =============================================================================
# Short-Test-Pipeline (Steps 0–4)
# =============================================================================

def short_test_pipeline(context=None, tracks_to_delete=None, report_fn=None):
    """Führt fünf Standardtests (Baseline, Step1–4) aus und persistiert sie in der Szene."""
    scene = (context.scene if context else bpy.context.scene)
    results = {"baseline": 0, "step1": 0, "step2": 0, "step3": 0, "step4": 0}

    # --- Baseline ---
    try:
        set_scene_props(scene,
            kaiserlich_rot_thresh_x=1.0, kaiserlich_rot_thresh_y=1.0,
            kaiserlich_scale_thresh_min=1.0, kaiserlich_scale_thresh_max=1.0,
            kaiserlich_rot_scale_thresh_rot=1.0, kaiserlich_rot_scale_thresh_scale=1.0,
            kaiserlich_perspective_thresh=1.0
        )
        res = short_test_track(context, tracks_to_delete, {"tag": "BASELINE"}, report_fn)
        results["baseline"] = int(float(res.get("total_track_length", 0.0)))
        scene[SCENE_TOTAL_TRACK_LEN_BASE] = results["baseline"]
    except Exception:
        pass

    # --- Step 1 ---
    try:
        set_scene_props(scene, kaiserlich_rot_thresh_x=0.0, kaiserlich_rot_thresh_y=0.0)
        res = short_test_track(context, None, {"tag": "STEP1"}, report_fn)
        results["step1"] = int(float(res.get("total_track_length", 0.0)))
        scene[SCENE_TOTAL_TRACK_LEN_STEP1] = results["step1"]
    except Exception:
        pass

    # --- Step 2 ---
    try:
        set_scene_props(scene,
            kaiserlich_rot_thresh_x=1.0, kaiserlich_rot_thresh_y=1.0,
            kaiserlich_scale_thresh_min=0.0, kaiserlich_scale_thresh_max=0.0
        )
        res = short_test_track(context, None, {"tag": "STEP2"}, report_fn)
        results["step2"] = int(float(res.get("total_track_length", 0.0)))
        scene[SCENE_TOTAL_TRACK_LEN_STEP2] = results["step2"]
    except Exception:
        pass

    # --- Step 3 ---
    try:
        set_scene_props(scene,
            kaiserlich_scale_thresh_min=1.0, kaiserlich_scale_thresh_max=1.0,
            kaiserlich_rot_scale_thresh_rot=0.0, kaiserlich_rot_scale_thresh_scale=0.0
        )
        res = short_test_track(context, None, {"tag": "STEP3"}, report_fn)
        results["step3"] = int(float(res.get("total_track_length", 0.0)))
        scene[SCENE_TOTAL_TRACK_LEN_STEP3] = results["step3"]
    except Exception:
        pass

    # --- Step 4 ---
    try:
        set_scene_props(scene,
            kaiserlich_rot_scale_thresh_rot=1.0,
            kaiserlich_rot_scale_thresh_scale=1.0,
            kaiserlich_perspective_thresh=0.0
        )
        res = short_test_track(context, None, {"tag": "STEP4"}, report_fn)
        results["step4"] = int(float(res.get("total_track_length", 0.0)))
        scene[SCENE_TOTAL_TRACK_LEN_STEP4] = results["step4"]
    except Exception:
        pass

    set_scene_props(scene, kaiserlich_perspective_thresh=1.0)
    return results


# =============================================================================
# Vergleich
# =============================================================================

def _get_scene_int(scene: bpy.types.Scene, key: str) -> Optional[int]:
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
    """Vergleicht STEP1–STEP4 gegen BASELINE und liefert Relationen."""
    scene = (context.scene if context else bpy.context.scene)
    base = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_BASE)
    v1 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP1)
    v2 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP2)
    v3 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP3)
    v4 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP4)

    values = {"STEP1": v1, "STEP2": v2, "STEP3": v3, "STEP4": v4}
    def _rel(v, b):
        if v is None or b is None: return "missing"
        if v > b: return "better"
        if v == b: return "equal"
        return "worse"

    relations = {k: _rel(v, base) for k, v in values.items()}
    better_or_equal = [k for k, r in relations.items() if r in ("better", "equal")]
    all_present = (base is not None) and all(v is not None for v in values.values())

    return {
        "baseline": base,
        "values": values,
        "relations": relations,
        "better_or_equal": better_or_equal,
        "all_present": all_present,
    }