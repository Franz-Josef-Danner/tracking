import bpy
from typing import Any, Dict, List, Optional, Tuple
from ..Helper.util_scene import set_scene_props
from ..Helper.util_thresholds import snapshot_thresholds, restore_thresholds
from ..Helper.util_shorttest import short_test_track

# Zusätzliche Helper für rückwärts Inline-Tracking
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.collect_selected_tracks import collect_selected_track_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.util_clip import get_current_track_names
from ..Helper.track_length_helper import get_total_track_length


# ---------------------------------------------------------------------------
# Scene Keys
# ---------------------------------------------------------------------------
SCENE_DEEPTEST_ROT_XY_BEST        = "kaiserlich_deeptest_rot_xy_best"
SCENE_DEEPTEST_SCALE_BEST         = "kaiserlich_deeptest_scale_best"
SCENE_DEEPTEST_ROT_SCALE_BEST     = "kaiserlich_deeptest_rot_scale_best"
SCENE_DEEPTEST_PERSPECTIVE_BEST   = "kaiserlich_deeptest_perspective_best"


# ---------------------------------------------------------------------------
# INLINE BACKWARD TRACKING
# ---------------------------------------------------------------------------
def run_backward_track_inline(context) -> Dict[str, Any]:
    """Führt einen vollständigen Rückwärts-Tracking-Zyklus inline aus."""
    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        raise RuntimeError("Kein aktiver Clip (Backwards Inline).")

    window, area, region, space = find_clip_editor_area(clip)
    if not window:
        raise RuntimeError("Keine CLIP_EDITOR Area gefunden (Backwards Inline).")

    start_frame = getattr(scene, "frame_start", 1)
    end_frame = getattr(scene, "frame_end", start_frame)
    if end_frame < start_frame:
        end_frame = start_frame

    selected = collect_selected_tracks(context)
    if not selected:
        raise RuntimeError("Keine Tracks selektiert (Backwards Inline).")

    processing_names = list(selected)
    frames_processed = 0
    print("[Kaiserlich Tracker][InlineBackwards] ▶ Starte Rückwärts-Tracking-Zyklus...")

    for current_frame in range(end_frame, start_frame - 1, -1):
        space.clip_user.frame_current = current_frame
        scene.frame_current = current_frame

        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[Kaiserlich Tracker][InlineBackwards] ⚠️ Formel-Fehler: {e}")

        success = track_markers_with_override(
            window, area, region, space,
            backwards=True, sequence=False
        )
        if not success:
            print("[Kaiserlich Tracker][InlineBackwards] ⚠️ Tracking-Fehler, Abbruch.")
            break

        frames_processed += 1
        processing_names, _ = filter_active_tracks_at_frame(context, processing_names, current_frame)

        if current_frame <= start_frame:
            print("[Kaiserlich Tracker][InlineBackwards] ✅ Szenenstart erreicht.")
            break
        if not processing_names:
            print("[Kaiserlich Tracker][InlineBackwards] ✅ Keine aktiven Tracks mehr.")
            break

    try:
        reset_to_frame(context, start_frame)
    except Exception as e:
        print(f"[Kaiserlich Tracker][InlineBackwards] ⚠️ Reset-Fehler: {e}")

    print("[Kaiserlich Tracker][InlineBackwards] ✅ Zyklus abgeschlossen.")
    total_len = float(get_total_track_length(context))
    return {"total_track_length": total_len, "frames_processed": frames_processed}


# ---------------------------------------------------------------------------
# GENERISCHES GRID (mit Vorwärts + Rückwärts)
# ---------------------------------------------------------------------------
def run_grid(context, apply_params_fn, grid: List[Dict[str, float]],
             tracks_to_delete=None, persist_best_key=None) -> Dict[str, Any]:
    scene = (context.scene if context else bpy.context.scene)
    snap = snapshot_thresholds(scene)

    measurements: List[Dict[str, Any]] = []
    best_len = -1
    best_cfg = {}
    best_idx = -1

    try:
        for i, cfg in enumerate(grid):
            try:
                apply_params_fn(scene, cfg)
            except Exception as e:
                measurements.append({"index": i, "params": cfg, "error": str(e)})
                continue

            try:
                # --- Vorwärtslauf (DetectAdapt + TrackCycle)
                res_fwd = short_test_track(context=context, tracks_to_delete=tracks_to_delete)
                ttl_fwd = int(float(res_fwd.get("total_track_length", 0.0)))

                # --- Rückwärtslauf
                res_bwd = run_backward_track_inline(context)
                ttl_bwd = int(float(res_bwd.get("total_track_length", 0.0)))

                ttl_combined = ttl_fwd + ttl_bwd
                print(f"[Kaiserlich Tracker][DeepTest] Index={i} → FWD={ttl_fwd}, BWD={ttl_bwd}, SUM={ttl_combined}")
            except Exception as e:
                ttl_combined = 0
                res_fwd = {"error": str(e)}
                res_bwd = {}
                print(f"[Kaiserlich Tracker][DeepTest] ⚠️ Fehler bei Index {i}: {e}")

            measurements.append({
                "index": i,
                "params": cfg,
                "forward": res_fwd,
                "backward": res_bwd,
                "total_track_length": ttl_combined
            })

            if ttl_combined > best_len:
                best_len, best_cfg, best_idx = ttl_combined, cfg, i

        if persist_best_key and best_len >= 0:
            scene[persist_best_key] = int(best_len)
    finally:
        restore_thresholds(scene, snap)

    return {
        "measurements": measurements,
        "best": {"index": best_idx, "params": best_cfg, "total_track_length": best_len}
    }


# ---------------------------------------------------------------------------
# SPEZIALISIERTE DEEP-TESTS
# ---------------------------------------------------------------------------
def deep_test_rot_xy(context=None, grid=None, tracks_to_delete=None):
    if grid is None:
        grid = [(0.0, 0.0), (0.01, 0.01), (0.05, 0.05), (0.1, 0.1), (0.2, 0.2), (0.5, 0.5)]
    def _apply(scene, cfg): set_scene_props(scene, **cfg)
    grid_dicts = [{"kaiserlich_rot_thresh_x": x, "kaiserlich_rot_thresh_y": y} for (x, y) in grid]
    return run_grid(context, _apply, grid_dicts, tracks_to_delete, SCENE_DEEPTEST_ROT_XY_BEST)


def deep_test_scale_min_max(context=None, grid=None, tracks_to_delete=None):
    if grid is None:
        grid = [(0.0, 0.0), (0.005, 0.005), (0.01, 0.01), (0.05, 0.05), (0.1, 0.1), (0.2, 0.2)]
    def _apply(scene, cfg): set_scene_props(scene, **cfg)
    grid_dicts = [{"kaiserlich_scale_thresh_min": mn, "kaiserlich_scale_thresh_max": mx} for (mn, mx) in grid]
    return run_grid(context, _apply, grid_dicts, tracks_to_delete, SCENE_DEEPTEST_SCALE_BEST)


def deep_test_rot_scale_pair(context=None, grid=None, tracks_to_delete=None):
    if grid is None:
        grid = [(0.0, 0.0), (0.01, 0.01), (0.05, 0.05), (0.1, 0.1), (0.2, 0.2)]
    def _apply(scene, cfg): set_scene_props(scene, **cfg)
    grid_dicts = [{"kaiserlich_rot_scale_thresh_rot": r, "kaiserlich_rot_scale_thresh_scale": s} for (r, s) in grid]
    return run_grid(context, _apply, grid_dicts, tracks_to_delete, SCENE_DEEPTEST_ROT_SCALE_BEST)


def deep_test_perspective(context=None, values=None, tracks_to_delete=None):
    if values is None:
        values = [0.0, 0.005, 0.01, 0.02, 0.05, 0.1]
    def _apply(scene, cfg): set_scene_props(scene, **cfg)
    grid_dicts = [{"kaiserlich_perspective_thresh": v} for v in values]
    return run_grid(context, _apply, grid_dicts, tracks_to_delete, SCENE_DEEPTEST_PERSPECTIVE_BEST)