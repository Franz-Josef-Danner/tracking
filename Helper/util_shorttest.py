import bpy
from typing import Any, Dict, List, Optional, Set

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names
from ..Helper.util_scene import call_get_start_frame, call_reset_to_frame, set_scene_props
from ..Helper.util_clip import get_current_track_names
from ..Helper.util_format import fmt8

# zusätzlich importiert für Inline DetectAdapt
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
import math, time

# Scene Keys
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"


# ---------------------------------------------------------------------------
#  SHORT TEST  (DetectAdapt inline, ohne Operator)
# ---------------------------------------------------------------------------
def short_test_track(
    context=None,
    tracks_to_delete=None,
    run_meta: Optional[Dict[str, Any]] = None,
    report_fn: Optional[Any] = None
):
    """Führt einen einzelnen Short-Test aus (Detect, Track, Delete, Reset)."""
    start_frame = None
    deleted_explicit: List[str] = []
    deleted_new: List[str] = []
    final_total_len: float = 0.0

    def _safe_get(scene, name):
        try:
            return float(getattr(scene, name))
        except Exception:
            return None

    scene = (context.scene if context else bpy.context.scene)
    if run_meta is None:
        run_meta = {}

    fields: List[str] = run_meta.get("fields") or [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]
    tag: str = run_meta.get("tag") or "TEST"
    sf = run_meta.get("sf", None)

    kv = []
    for f in fields:
        v = _safe_get(scene, f)
        if v is not None:
            kv.append(f"{f}={fmt8(v)}")
    if sf is not None:
        kv.insert(0, f"sf={fmt8(sf)}")
    if report_fn and kv:
        report_fn(f"[{tag}] " + " | ".join(kv))

    pre_names: Set[str] = get_current_track_names(context)

    try:
        snapshot_active_markers(context)

        # ------------------------------------------------------------------
        # DetectAdapt Inline Flow (anstelle des Operatoraufrufs)
        # ------------------------------------------------------------------
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            raise RuntimeError("Kein aktiver Clip gefunden (DetectAdapt-Flow).")

        hz, vc = clip.size
        tracking_settings = getattr(clip.tracking, "settings", None)
        ma = getattr(tracking_settings, "margin", 100)
        pz = getattr(tracking_settings, "pattern_size", 50)
        sz = getattr(tracking_settings, "search_size", 100)
        ef_target = int(scene.kaiserlich_markers_per_frame)

        md = hz * 0.025
        tr = 0.0001

        pre_snapshot = snapshot_active_markers(context)
        baseline_start_tracknames = {t.name for t in clip.tracking.tracks}

        max_loops = 8
        loop = 0
        last_md = md

        while loop < max_loops:
            loop += 1
            print(f"\n[Kaiserlich Tracker][ShortTest][DetectAdapt] LOOP {loop} | min_distance={last_md:.2f}")

            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(last_md)))
            )

            for trk in clip.tracking.tracks:
                try:
                    trk.select = False
                except Exception:
                    pass

            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            cleaned_new, deleted_old = cleanup_new_markers(context, alte_marker, neue_marker, pz=pz, hz=hz, vc=vc)

            print(f"[Kaiserlich Tracker][ShortTest][DetectAdapt] Neue Marker: {len(cleaned_new)} | Alte gelöscht: {deleted_old}")

            remaining = len(cleaned_new)
            diff = remaining - ef_target
            tolerance = ef_target * 0.10
            if abs(diff) <= tolerance:
                print(f"[Kaiserlich Tracker][ShortTest][DetectAdapt] Ziel erreicht ({remaining}/{ef_target})")
                break

            if len(cleaned_new) > 0:
                ratio = ef_target / len(cleaned_new)
                factor = max(0.5, min(2.0, ratio))
                last_md = max(1.0, last_md / factor)
            else:
                last_md *= 1.5
                print("[Kaiserlich Tracker][ShortTest][DetectAdapt] Keine neuen Marker → erhöhe min_distance.")

            if loop < max_loops:
                delete_tracks_by_names(context, [m['track'] for m in neue_marker])
                time.sleep(0.1)

        for trk in clip.tracking.tracks:
            trk.select = (trk.name not in baseline_start_tracknames)

        print(f"[Kaiserlich Tracker][ShortTest][DetectAdapt] Final selektierte Marker: "
              f"{len([t for t in clip.tracking.tracks if t.select])}")

        # ------------------------------------------------------------------
        # Danach: Tracking per Operator (bleibt unverändert)
        # ------------------------------------------------------------------
        start_frame = call_get_start_frame(context)
        if 'CANCELLED' in bpy.ops.kaiserlich_tracker.track_cycle('EXEC_DEFAULT'):
            raise RuntimeError("Tracking abgebrochen.")

        if tracks_to_delete:
            names = [n.strip() for n in tracks_to_delete if n and n.strip()]
            if names:
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
            post_names: Set[str] = get_current_track_names(context)
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


# ---------------------------------------------------------------------------
#  SHORT-TEST PIPELINE
# ---------------------------------------------------------------------------
def short_test_pipeline(context=None, tracks_to_delete=None, report_fn=None):
    """Führt BASELINE + 4 Steps aus und persistiert deren Längen."""
    scene = (context.scene if context else bpy.context.scene)
    results = {"baseline": 0, "step1": 0, "step2": 0, "step3": 0, "step4": 0}

    def _save_scene_key(key, val):
        try:
            scene[key] = int(val)
        except Exception:
            pass

    # Baseline
    set_scene_props(scene,
        kaiserlich_rot_thresh_x=1.0, kaiserlich_rot_thresh_y=1.0,
        kaiserlich_scale_thresh_min=1.0, kaiserlich_scale_thresh_max=1.0,
        kaiserlich_rot_scale_thresh_rot=1.0, kaiserlich_rot_scale_thresh_scale=1.0,
        kaiserlich_perspective_thresh=1.0)
    rb = short_test_track(context, tracks_to_delete, {"tag": "BASELINE"}, report_fn)
    results["baseline"] = int(rb["total_track_length"]); _save_scene_key(SCENE_TOTAL_TRACK_LEN_BASE, results["baseline"])

    # Step1
    set_scene_props(scene, kaiserlich_rot_thresh_x=0.0, kaiserlich_rot_thresh_y=0.0)
    r1 = short_test_track(context, None, {"tag": "STEP1"}, report_fn)
    results["step1"] = int(r1["total_track_length"]); _save_scene_key(SCENE_TOTAL_TRACK_LEN_STEP1, results["step1"])

    # Step2
    set_scene_props(scene, kaiserlich_rot_thresh_x=1.0, kaiserlich_rot_thresh_y=1.0,
                    kaiserlich_scale_thresh_min=0.0, kaiserlich_scale_thresh_max=0.0)
    r2 = short_test_track(context, None, {"tag": "STEP2"}, report_fn)
    results["step2"] = int(r2["total_track_length"]); _save_scene_key(SCENE_TOTAL_TRACK_LEN_STEP2, results["step2"])

    # Step3
    set_scene_props(scene, kaiserlich_scale_thresh_min=1.0, kaiserlich_scale_thresh_max=1.0,
                    kaiserlich_rot_scale_thresh_rot=0.0, kaiserlich_rot_scale_thresh_scale=0.0)
    r3 = short_test_track(context, None, {"tag": "STEP3"}, report_fn)
    results["step3"] = int(r3["total_track_length"]); _save_scene_key(SCENE_TOTAL_TRACK_LEN_STEP3, results["step3"])

    # Step4
    set_scene_props(scene, kaiserlich_rot_scale_thresh_rot=1.0, kaiserlich_rot_scale_thresh_scale=1.0,
                    kaiserlich_perspective_thresh=0.0)
    r4 = short_test_track(context, None, {"tag": "STEP4"}, report_fn)
    results["step4"] = int(r4["total_track_length"]); _save_scene_key(SCENE_TOTAL_TRACK_LEN_STEP4, results["step4"])

    set_scene_props(scene, kaiserlich_perspective_thresh=1.0)
    return results


# ---------------------------------------------------------------------------
#  COMPARISON UTILITIES
# ---------------------------------------------------------------------------
def _get_scene_int(scene: bpy.types.Scene, key: str) -> Optional[int]:
    try:
        if key in scene.keys(): val = scene[key]
        elif hasattr(scene, key): val = getattr(scene, key)
        else: return None
        return int(float(val))
    except Exception:
        return None


def compare_len_steps_to_total(context=None):
    """Vergleicht STEP1..STEP4 gegen Baseline."""
    scene = (context.scene if context else bpy.context.scene)
    base = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_BASE)
    v1 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP1)
    v2 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP2)
    v3 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP3)
    v4 = _get_scene_int(scene, SCENE_TOTAL_TRACK_LEN_STEP4)

    values = {"STEP1": v1, "STEP2": v2, "STEP3": v3, "STEP4": v4}
    relations = {}

    def _rel(v, b):
        if v is None or b is None: return "missing"
        if v > b: return "better"
        if v == b: return "equal"
        return "worse"

    for k, v in values.items():
        relations[k] = _rel(v, base)

    better_or_equal = [k for k, r in relations.items() if r in ("better", "equal")]
    all_present = (base is not None) and all(v is not None for v in values.values())
    return {"baseline": base, "values": values, "relations": relations, "better_or_equal": better_or_equal, "all_present": all_present}