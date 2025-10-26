import bpy
from typing import Any, Dict, List, Optional, Tuple
from ..Helper.util_scene import set_scene_props
from ..Helper.util_thresholds import snapshot_thresholds, restore_thresholds
from ..Helper.util_shorttest import short_test_track

SCENE_DEEPTEST_ROT_XY_BEST        = "kaiserlich_deeptest_rot_xy_best"
SCENE_DEEPTEST_SCALE_BEST         = "kaiserlich_deeptest_scale_best"
SCENE_DEEPTEST_ROT_SCALE_BEST     = "kaiserlich_deeptest_rot_scale_best"
SCENE_DEEPTEST_PERSPECTIVE_BEST   = "kaiserlich_deeptest_perspective_best"


# ---------------------------------------------------------------------------
# GENERISCHES GRID
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
                res = short_test_track(context=context, tracks_to_delete=tracks_to_delete)
                ttl = int(float(res.get("total_track_length", 0.0)))
            except Exception as e:
                ttl = 0
                res = {"error": f"short_test_failed: {e}"}

            measurements.append({"index": i, "params": cfg, "total_track_length": ttl, "meta": res})
            if ttl > best_len:
                best_len, best_cfg, best_idx = ttl, cfg, i

        if persist_best_key and best_len >= 0:
            scene[persist_best_key] = int(best_len)
    finally:
        restore_thresholds(scene, snap)

    return {"measurements": measurements, "best": {"index": best_idx, "params": best_cfg, "total_track_length": best_len}}


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