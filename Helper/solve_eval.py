from dataclasses import dataclass
from typing import Literal, Sequence
import bpy, statistics as st, random

DistModel = Literal["POLYNOMIAL", "DIVISION", "BROWN"]


@dataclass
class SolveConfig:
    holdout_ratio: float = 0.15
    holdout_grid: tuple[int, int] = (3, 3)
    holdout_edge_boost: float = 1.4
    parallax_delta: int = 5
    refine_rounds: int = 2              # R1: f+K1, R2: +K2
    center_box: float = 0.6             # 60% zentrales Rechteck
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


# --------- Clip/Objekt/Frames ----------
def _get_clip_and_objects(context):
    clip = (
        getattr(context, "edit_movieclip", None)
        or getattr(getattr(context, "space_data", None), "clip", None)
        or getattr(context.scene, "active_clip", None)
    )
    if clip is None:
        raise RuntimeError("No active MovieClip found.")
    tr = clip.tracking
    obj = tr.objects.active or (tr.objects[0] if len(tr.objects) else None)
    if obj is None:
        raise RuntimeError("No MovieTrackingObject found.")
    return clip, tr, obj


def _clip_frame_range(clip):
    fs = int(getattr(clip, "frame_start", 1))
    fd = int(getattr(clip, "frame_duration", 0))
    if fd > 0:
        return fs, fs + fd - 1
    frames = []
    tr = clip.tracking
    tracks = tr.objects.active.tracks if tr.objects.active else tr.tracks
    for t in tracks:
        frames.extend([mk.frame for mk in t.markers])
    if frames:
        return min(frames), max(frames)
    scn = bpy.context.scene
    return int(getattr(scn, "frame_start", 1)), int(getattr(scn, "frame_end", 1))


# --------- Parallaxe ----------
def compute_parallax_scores(clip, delta=5):
    tr = clip.tracking
    tracks = tr.objects.active.tracks if tr.objects.active else tr.tracks
    fs, fe = _clip_frame_range(clip)
    f0, f1 = int(fs + delta), int(fe - delta)
    if f1 <= f0:
        return []
    out = []
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


# --------- Hold-outs ----------
def choose_holdouts(clip, ratio=0.15, grid=(3, 3), edge_boost=1.4):
    tr = clip.tracking
    tracks = tr.objects.active.tracks if tr.objects.active else tr.tracks
    items = []
    for t in tracks:
        if not t.markers:
            continue
        mk = max(t.markers, key=lambda m: m.frame)
        x, y = mk.co
        items.append((t, x, y))
    if not items:
        return set()
    gx, gy = grid
    buckets = {}
    for t, x, y in items:
        ix = min(gx - 1, max(0, int(x * gx)))
        iy = min(gy - 1, max(0, int(y * gy)))
        buckets.setdefault((ix, iy), []).append((t, x, y))

    def cell_weight(ix, iy):
        edge_x = (ix == 0 or ix == gx - 1)
        edge_y = (iy == 0 or iy == gy - 1)
        return edge_boost if (edge_x or edge_y) else 1.0

    total = len(items)
    target = max(1, int(total * ratio))
    selected = set()
    weights = {k: cell_weight(*k) * len(v) for k, v in buckets.items()}
    weight_sum = sum(weights.values()) or 1.0
    quota = {k: max(0, int(target * (w / weight_sum))) for k, w in weights.items()}
    for k, q in quota.items():
        random.shuffle(buckets[k])
        for i in range(min(q, len(buckets[k]))):
            selected.add(buckets[k][i][0])
    if len(selected) < target:
        rest = [t for t, _, _ in items if t not in selected]
        random.shuffle(rest)
        for t in rest[: target - len(selected)]:
            selected.add(t)
    return selected


def set_holdout_weights(tracks: set, w: float):
    for t in tracks:
        try:
            t.weight = w
        except Exception:
            pass


# --------- Metriken & Score ----------
def collect_metrics(clip, holdouts: set, center_box=0.6):
    hs = [t.average_error for t in holdouts if getattr(t, "average_error", 0) > 0]
    hold_med = st.median(hs) if hs else 999.0
    hold_p95 = (
        st.quantiles(hs, n=20)[-1] if len(hs) >= 20 else (max(hs) if hs else 999.0)
    )
    cx0 = cy0 = (1 - center_box) / 2.0
    cx1 = cy1 = 1 - cx0
    edge_errs, center_errs = [], []
    tr = clip.tracking
    tracks = tr.objects.active.tracks if tr.objects.active else tr.tracks
    for t in tracks:
        mk = max(t.markers, key=lambda m: m.frame, default=None)
        if not mk:
            continue
        x, y = mk.co
        (edge_errs if (x < cx0 or x > cx1 or y < cy0 or y > cy1) else center_errs).append(
            getattr(t, "average_error", 0)
        )
    edge_gap = (
        st.median(edge_errs) - st.median(center_errs)
        if edge_errs and center_errs
        else 0.0
    )
    fs, fe = _clip_frame_range(clip)
    total = max(1, fe - fs + 1)
    lens = [
        (t.markers[-1].frame - t.markers[0].frame + 1)
        for t in tracks
        if len(t.markers) >= 2
    ]
    persist = (sum(lens) / len(lens) / total) if lens else 0.0
    return hold_med, hold_p95, edge_gap, persist


def score_metrics(med, p95, edge_gap, persist, fov_dev_norm, w=None):
    if not w:
        w = {"med": 1.0, "p95": 0.5, "fov": 0.3, "persist": 0.3, "edge": 0.4}
    return (
        w["med"] * med
        + w["p95"] * p95
        + w["fov"] * fov_dev_norm
        + w["persist"] * (1 - persist)
        + w["edge"] * max(0.0, edge_gap)
    )


# --------- Solve (mit UI-Invoke) ----------
def _invoke_solve_ui(context):
    """Nutzt Helper, der INVOKE_DEFAULT triggert."""
    try:
        from .solve_camera import solve_camera_only
        return solve_camera_only(context)
    except Exception:
        try:
            return bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        except Exception as e:
            raise RuntimeError(f"Solve invoke failed: {e!r}")


def _set_refine_stage(tr_settings, stage: int):
    flags = set()
    if stage >= 1:
        flags.update({"FOCAL_LENGTH", "RADIAL_K1"})
    if stage >= 2:
        flags.update({"RADIAL_K2"})
    try:
        tr_settings.refine_intrinsics = flags
    except Exception:
        pass


# --------- Hauptfunktion ----------
def run_solve_eval(context, config: SolveConfig):
    clip, tr, obj = _get_clip_and_objects(context)
    tr_settings = tr.settings
    fs, fe = _clip_frame_range(clip)

    # 1) Parallaxe → Keyframes setzen (Auto-Select aus)
    auto_prev = bool(tr_settings.use_keyframe_selection)
    tr_settings.use_keyframe_selection = False
    scores = compute_parallax_scores(clip, delta=config.parallax_delta)
    if scores:
        f, _ = scores[0]
        obj.keyframe_a = max(int(f - config.parallax_delta), int(fs))
        obj.keyframe_b = min(int(f + config.parallax_delta), int(fe))
    else:
        mid = (fs + fe) // 2
        obj.keyframe_a = max(fs, mid - config.parallax_delta)
        obj.keyframe_b = min(fe, mid + config.parallax_delta)

    # 2) Hold-outs wählen & setzen
    holdouts = choose_holdouts(
        clip,
        ratio=config.holdout_ratio,
        grid=config.holdout_grid,
        edge_boost=config.holdout_edge_boost,
    )
    orig_w = {t: getattr(t, "weight", 1.0) for t in holdouts}
    set_holdout_weights(holdouts, 0.0)

    # 3) Modell-Loop (ohne NUKE)
    models: Sequence[DistModel] = ("POLYNOMIAL", "DIVISION", "BROWN")
    all_metrics: list[SolveMetrics] = []

    cam = clip.tracking.camera
    f_nom = float(getattr(cam, "focal_length", 0.0)) or 0.0

    try:
        for model in models:
            cam.distortion_model = model
            for stage in range(1, config.refine_rounds + 1):
                _set_refine_stage(tr_settings, stage)
                _invoke_solve_ui(context)

                hold_med, hold_p95, edge_gap, persist = collect_metrics(
                    clip, holdouts, center_box=config.center_box
                )
                f_solved = float(getattr(cam, "focal_length", 0.0)) or f_nom
                fov_dev_norm = abs(f_solved - f_nom) / f_nom if f_nom > 0 else 0.0
                score = score_metrics(
                    hold_med,
                    hold_p95,
                    edge_gap,
                    persist,
                    fov_dev_norm,
                    config.score_w,
                )
                all_metrics.append(
                    SolveMetrics(
                        model=model,
                        refine_stage=stage,
                        holdout_med_px=hold_med,
                        holdout_p95_px=hold_p95,
                        edge_gap_px=edge_gap,
                        fov_dev_norm=fov_dev_norm,
                        persist=persist,
                        score=score,
                    )
                )
    finally:
        for t, w in orig_w.items():
            try:
                t.weight = w
            except Exception:
                pass
        tr_settings.use_keyframe_selection = auto_prev

    if not all_metrics:
        raise RuntimeError("No solve metrics produced.")
    best = min(
        all_metrics, key=lambda m: (m.score, m.holdout_p95_px, m.edge_gap_px)
    )
    cam.distortion_model = best.model
    _set_refine_stage(tr_settings, best.refine_stage)
    _invoke_solve_ui(context)

    return best.model, best, all_metrics
