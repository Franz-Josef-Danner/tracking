from __future__ import annotations
import bpy
from dataclasses import dataclass
from typing import Literal, Sequence, Iterable
import random
import statistics as st

DistModel = Literal["POLYNOMIAL", "DIVISION", "BROWN"]


@dataclass
class SolveConfig:
    holdout_ratio: float = 0.15
    holdout_grid: tuple[int, int] = (3, 3)
    holdout_edge_boost: float = 1.4
    parallax_delta: int = 5
    parallax_topk: int = 1
    refine_rounds: int = 2
    enable_brown_tangential_if_asym: bool = True
    center_box: float = 0.6
    fov_warn_pct: float = 0.15
    score_w: dict[str, float] | None = None


@dataclass
class SolveMetrics:
    model: DistModel
    refine_stage: int
    holdout_med_px: float
    holdout_p95_px: float
    edge_gap_px: float
    fov_dev_norm: float
    persist: float
    score: float


__all__ = ("run_solve_eval", "SolveConfig", "SolveMetrics", "DistModel")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_clip(context: bpy.types.Context):
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip


def _ensure_clip_context(context: bpy.types.Context) -> dict:
    wm = bpy.context.window_manager
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {
                    "window": win,
                    "area": area,
                    "region": region,
                    "space_data": space,
                    "scene": bpy.context.scene,
                }
    return {}


def _apply_refine_flags(settings, *, focal: bool, principal: bool, radial: bool, tangential: bool = False) -> None:
    try:
        if hasattr(settings, "refine_intrinsics_focal_length"):
            settings.refine_intrinsics_focal_length = bool(focal)
        if hasattr(settings, "refine_intrinsics_principal_point"):
            settings.refine_intrinsics_principal_point = bool(principal)
        if hasattr(settings, "refine_intrinsics_radial_distortion"):
            settings.refine_intrinsics_radial_distortion = bool(radial)
        if hasattr(settings, "refine_intrinsics_tangential_distortion"):
            settings.refine_intrinsics_tangential_distortion = bool(tangential)
    except Exception:
        pass


def compute_parallax_scores(clip, delta: int = 5):
    tracks = [t for t in clip.tracking.tracks if len(t.markers) > 2 * delta]
    f0, f1 = int(clip.frame_start + delta), int(clip.frame_end - delta)
    out: list[tuple[int, float]] = []
    for f in range(f0, f1 + 1):
        vecs = []
        for t in tracks:
            m0 = t.markers.find_frame(f - delta, exact=True)
            m1 = t.markers.find_frame(f + delta, exact=True)
            if m0 and m1:
                vecs.append((m1.co[0] - m0.co[0], m1.co[1] - m0.co[1]))
        if len(vecs) > 8:
            mx = sum(v[0] for v in vecs) / len(vecs)
            my = sum(v[1] for v in vecs) / len(vecs)
            resid = [((vx - mx) ** 2 + (vy - my) ** 2) ** 0.5 for vx, vy in vecs]
            mu = sum(resid) / len(resid)
            std = (sum((r - mu) ** 2 for r in resid) / len(resid)) ** 0.5
            out.append((f, std))
    return sorted(out, key=lambda x: x[1], reverse=True)


def choose_holdouts(tracks: Sequence[bpy.types.MovieTrackingTrack], *, keyframe: int, ratio: float = 0.15, grid: tuple[int, int] = (3, 3), edge_boost: float = 1.4) -> set[bpy.types.MovieTrackingTrack]:
    gx, gy = grid
    cells: dict[tuple[int, int], list[bpy.types.MovieTrackingTrack]] = {}
    for t in tracks:
        m = t.markers.find_frame(keyframe, exact=True)
        if not m:
            continue
        x, y = m.co
        ix = min(gx - 1, int(x * gx))
        iy = min(gy - 1, int(y * gy))
        cells.setdefault((ix, iy), []).append(t)
    cell_items = list(cells.items())
    weights = []
    for (ix, iy), ts in cell_items:
        is_edge = ix in {0, gx - 1} or iy in {0, gy - 1}
        weights.append(len(ts) * (edge_boost if is_edge else 1.0))
    total_tracks = sum(len(ts) for _, ts in cell_items)
    target = max(1, int(total_tracks * ratio))
    chosen: set[bpy.types.MovieTrackingTrack] = set()
    if total_tracks == 0:
        return chosen
    while len(chosen) < target:
        cell, ts = random.choices(cell_items, weights=weights, k=1)[0]
        t = random.choice(ts)
        chosen.add(t)
        if len(chosen) >= target:
            break
    return chosen


def set_holdout_weights(tracks: Iterable[bpy.types.MovieTrackingTrack], w: float) -> None:
    for t in tracks:
        try:
            t.weight = w
        except Exception:
            pass


def collect_metrics(clip, holdouts: Iterable[bpy.types.MovieTrackingTrack], *, center_box: float = 0.6):
    hs = [t.average_error for t in holdouts if t.average_error > 0]
    hold_med = st.median(hs) if hs else 999.0
    hold_p95 = st.quantiles(hs, n=20)[-1] if len(hs) >= 20 else (max(hs) if hs else 999.0)
    cx0, cy0 = (1 - center_box) / 2, (1 - center_box) / 2
    cx1, cy1 = 1 - cx0, 1 - cy0
    edge_errs, center_errs = [], []
    left, right, top, bottom = [], [], [], []
    for t in clip.tracking.tracks:
        m = max(t.markers, key=lambda mk: mk.frame, default=None)
        if not m:
            continue
        x, y = m.co
        if x < cx0 or x > cx1 or y < cy0 or y > cy1:
            edge_errs.append(t.average_error)
            if x < cx0:
                left.append(t.average_error)
            if x > cx1:
                right.append(t.average_error)
            if y < cy0:
                bottom.append(t.average_error)
            if y > cy1:
                top.append(t.average_error)
        else:
            center_errs.append(t.average_error)
    edge_gap = (st.median(edge_errs) - st.median(center_errs)) if edge_errs and center_errs else 0.0
    lr_diff = abs(st.median(left) - st.median(right)) if left and right else 0.0
    tb_diff = abs(st.median(top) - st.median(bottom)) if top and bottom else 0.0
    total = clip.frame_end - clip.frame_start + 1
    lens = [(t.markers[-1].frame - t.markers[0].frame + 1) for t in clip.tracking.tracks if len(t.markers) >= 2]
    persist = (sum(lens) / len(lens) / total) if lens else 0.0
    return hold_med, hold_p95, edge_gap, persist, lr_diff, tb_diff


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_solve_eval(context, config: SolveConfig) -> tuple[str, SolveMetrics, list[SolveMetrics]]:
    clip = _resolve_clip(context)
    if not clip:
        raise RuntimeError("No movie clip available")
    tracks = [t for t in clip.tracking.tracks if len(t.markers) >= 2]
    if len(tracks) < 40:
        raise RuntimeError("Not enough valid tracks (<40)")

    tr_settings = clip.tracking.settings
    orig_key_sel = bool(getattr(tr_settings, "use_keyframe_selection", False))

    scores = compute_parallax_scores(clip, delta=config.parallax_delta)
    if scores:
        f = scores[0][0]
        tr_settings.keyframe_a = max(int(f - config.parallax_delta), int(clip.frame_start))
        tr_settings.keyframe_b = min(int(f + config.parallax_delta), int(clip.frame_end))
        tr_settings.use_keyframe_selection = False
    else:
        tr_settings.use_keyframe_selection = True

    keyframe_a = int(getattr(tr_settings, "keyframe_a", clip.frame_start))

    holdouts = choose_holdouts(tracks, keyframe=keyframe_a, ratio=config.holdout_ratio, grid=config.holdout_grid, edge_boost=config.holdout_edge_boost)
    set_holdout_weights(holdouts, 0.0)

    cam = clip.tracking.camera
    try:
        f_nominal = float(cam.focal_length)
    except Exception:
        f_nominal = 0.0

    metrics_all: list[SolveMetrics] = []
    brown_tangential = False

    w = config.score_w or {
        "holdout_med_px": 1.0,
        "holdout_p95_px": 0.5,
        "fov_dev_norm": 0.3,
        "persist": 0.3,
        "edge_gap_px": 0.4,
    }

    for model in ("POLYNOMIAL", "DIVISION", "BROWN"):
        cam.distortion_model = model
        for stage in range(1, config.refine_rounds + 1):
            tangential = False
            if model == "BROWN" and stage == 2 and config.enable_brown_tangential_if_asym and brown_tangential:
                tangential = True
            _apply_refine_flags(tr_settings, focal=True, principal=False, radial=True, tangential=tangential)
            if stage == 1:
                try:
                    cam.k2 = 0.0
                except Exception:
                    pass
            with context.temp_override(**_ensure_clip_context(context)):
                bpy.ops.clip.solve_camera()
            hold_med, hold_p95, edge_gap, persist, lr_diff, tb_diff = collect_metrics(clip, holdouts, center_box=config.center_box)
            try:
                solved_f = float(cam.focal_length)
                fov_dev = abs(solved_f - f_nominal) / f_nominal if f_nominal else 0.0
            except Exception:
                fov_dev = 0.0
            score = (
                w["holdout_med_px"] * hold_med
                + w["holdout_p95_px"] * hold_p95
                + w["fov_dev_norm"] * fov_dev
                + w["persist"] * (1 - persist)
                + w["edge_gap_px"] * edge_gap
            )
            met = SolveMetrics(
                model=model,
                refine_stage=stage,
                holdout_med_px=hold_med,
                holdout_p95_px=hold_p95,
                edge_gap_px=edge_gap,
                fov_dev_norm=fov_dev,
                persist=persist,
                score=score,
            )
            metrics_all.append(met)
            if model == "BROWN" and stage == 1 and config.enable_brown_tangential_if_asym:
                if max(lr_diff, tb_diff) > 0.15:
                    brown_tangential = True

    best = min(metrics_all, key=lambda m: (m.score, m.holdout_p95_px, m.edge_gap_px))
    winner = best.model

    set_holdout_weights(holdouts, 1.0)

    cam.distortion_model = winner
    tangential_final = brown_tangential if (winner == "BROWN" and best.refine_stage == 2 and config.enable_brown_tangential_if_asym) else False
    _apply_refine_flags(tr_settings, focal=True, principal=False, radial=True, tangential=tangential_final)
    if best.refine_stage == 1:
        try:
            cam.k2 = 0.0
        except Exception:
            pass
    with context.temp_override(**_ensure_clip_context(context)):
        bpy.ops.clip.solve_camera()

    tr_settings.use_keyframe_selection = orig_key_sel

    return winner, best, metrics_all
