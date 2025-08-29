"""Preflight-Helper für Blender-Tracking (erweitert)

Robuster Preflight für Frame-Paare mit Diagnostik, Fallback-Strategien und
reichhaltigen Metriken (Parallaxe, Homographie, Epipol, Skalierung). Ziel ist
es, verlässlich vor einem Solve einzuschätzen, ob sich ein Paar eignet und bei
Fehlversuchen automatisch alternative Varianten zu testen.

Abhängigkeiten: NumPy (Blender-bundled)
Lizenz: MIT
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence, Tuple

import bpy
import numpy as np

# =============================
# Datenstrukturen & API
# =============================

@dataclass
class PreSolveMetrics:
    """Ergebniscontainer für die Preflight-Messung eines Frame-Paars."""

    frame_a: int
    frame_b: int

    # RANSAC/Fundamental (Basis)
    inliers: int
    total: int
    median_sampson_px: float
    mean_sampson_px: float

    # Parallax & Abdeckung (Basis)
    parallax_median_px: float
    parallax_p95_px: float
    coverage_quadrants: float  # 0..1

    # Diagnose (Basis)
    degenerate: bool

    # Optional: Rohdaten
    F: Optional[np.ndarray] = None
    inlier_mask: Optional[np.ndarray] = None

    # Erweiterte Metriken
    inlier_ratio: Optional[float] = None
    coverage_area: Optional[float] = None
    quality_score: Optional[float] = None
    predicted_error: Optional[float] = None

    # Homographie-Indikatoren
    hom_inliers: Optional[int] = None
    hom_ratio: Optional[float] = None  # H-Inlier / F-Inlier

    # Epipol-Diagnostik
    epipole1_in_image: Optional[bool] = None
    epipole2_in_image: Optional[bool] = None

    # Radiale Skalierung (Vorwärts-/Rückwärtsfahrt)
    scale_median: Optional[float] = None
    scale_norm: Optional[float] = None

    # Übersicht, Variante, Root-Cause
    variant: Optional[str] = None
    fallback_attempt: Optional[int] = None
    reject_reason: Optional[str] = None
    root_cause: Optional[str] = None

    def as_dict(self) -> Dict:
        d = asdict(self)
        if isinstance(d.get("F"), np.ndarray):
            d["F"] = d["F"].tolist()
        if isinstance(d.get("inlier_mask"), np.ndarray):
            d["inlier_mask"] = np.asarray(d["inlier_mask"]).astype(bool).tolist()
        return d


# =============================
# Public API
# =============================

def scan_frame_pairs(
    clip: bpy.types.MovieClip,
    pairs: Sequence[Tuple[int, int]],
    *,
    ransac_thresh_px: float = 1.5,
    ransac_iters: int = 1000,
    min_track_len: int = 5,
    debug: bool = False,
    use_fallback: bool = False,
) -> List[PreSolveMetrics]:
    """Batch-Auswertung mehrerer Frame-Paare.
    Setzt optional Fallback-Strategien ein und loggt Zusammenfassungen.
    """
    results: List[PreSolveMetrics] = []
    for a, b in pairs:
        if use_fallback:
            m = estimate_pre_solve_with_fallback(
                clip,
                a,
                b,
                ransac_thresh_px=ransac_thresh_px,
                ransac_iters=ransac_iters,
                min_track_len=min_track_len,
                debug=debug,
            )
        else:
            m = estimate_pre_solve_metrics(
                clip,
                a,
                b,
                ransac_thresh_px=ransac_thresh_px,
                ransac_iters=ransac_iters,
                min_track_len=min_track_len,
                variant="default",
                debug=debug,
            )
        results.append(m)
    return results


def scan_scene(
    clip: Optional[bpy.types.MovieClip] = None,
    *,
    deltas: Sequence[int] = (8, 12, 16, 24, 32),
    stride: int = 10,
    ransac_thresh_px: float = 4.0,
    ransac_iters: int = 1000,
    min_track_len: int = 5,
    debug: bool = False,
    use_fallback: bool = False,
) -> List[PreSolveMetrics]:
    """Erzeugt automatisch viele Frame-Paare (coarse→fine) aus der Szene.
    Für jeden Startframe werden Paare mit verschiedenen Abständen "deltas"
    getestet (Start..Start+delta)."""
    if clip is None:
        clip = bpy.context.edit_movieclip
    if clip is None:
        raise RuntimeError("Kein aktiver MovieClip.")

    scene = bpy.context.scene
    s_start, s_end = int(scene.frame_start), int(scene.frame_end)

    pairs: List[Tuple[int,int]] = []
    for f in range(s_start, max(s_start, s_end - max(deltas)), max(1, stride)):
        for d in deltas:
            fb = f + d
            if fb <= s_end:
                pairs.append((f, fb))

    return scan_frame_pairs(
        clip,
        pairs,
        ransac_thresh_px=ransac_thresh_px,
        ransac_iters=ransac_iters,
        min_track_len=min_track_len,
        debug=debug,
        use_fallback=use_fallback,
    )


# --- Hauptfunktion -----------------------------------------------------------

def estimate_pre_solve_metrics(
    clip: bpy.types.MovieClip,
    frame_a: int,
    frame_b: int,
    *,
    ransac_thresh_px: float = 1.5,
    ransac_iters: int = 1000,
    min_track_len: int = 5,
    return_F_and_mask: bool = False,
    variant: Optional[str] = None,
    debug: bool = False,
) -> PreSolveMetrics:
    """Berechnet Pre-Solve-Kennzahlen für ein Frame-Paar (robust)."""

    def _gather(fa: int, fb: int):
        return _gather_tracks_for_frames(clip, fa, fb, min_length=min_track_len)

    # Frames direkt testen; ggf. mit Clip-Offset/Marker-Domäne nachfassen
    pts1, pts2, tracks = _gather(int(frame_a), int(frame_b))
    if (pts1 is None or len(pts1) < 8) and hasattr(clip, "frame_start"):
        off = int(getattr(clip, "frame_start", 1)) - 1
        pts1, pts2, tracks = _gather(int(frame_a) - off, int(frame_b) - off)
    if pts1 is None or len(pts1) < 8:
        all_tr = [tr for tr in clip.tracking.tracks if len(tr.markers) > 0]
        if all_tr:
            c_min = min(tr.markers[0].frame for tr in all_tr)
            s_start = int(bpy.context.scene.frame_start)
            off2 = s_start - c_min
            pts1, pts2, tracks = _gather(int(frame_a) - off2, int(frame_b) - off2)

    if pts1 is None or len(pts1) < 8:
        met = PreSolveMetrics(
            frame_a=int(frame_a), frame_b=int(frame_b),
            inliers=0, total=0 if pts1 is None else int(len(pts1)),
            median_sampson_px=float('inf'), mean_sampson_px=float('inf'),
            parallax_median_px=0.0, parallax_p95_px=0.0,
            coverage_quadrants=0.0, degenerate=True,
            F=None, inlier_mask=None,
            inlier_ratio=0.0, coverage_area=0.0,
            quality_score=0.0, predicted_error=float('inf'),
            hom_inliers=None, hom_ratio=None,
            epipole1_in_image=None, epipole2_in_image=None,
            scale_median=None, scale_norm=None,
            variant=variant or 'default', fallback_attempt=0,
            reject_reason='not_enough_points', root_cause='low_inliers',
        )
        if debug: _print_metric_summary(met)
        return met

    # Parallax/Abdeckung (alle Kandidaten)
    disp = np.linalg.norm(pts2 - pts1, axis=1)
    parallax_med = float(np.median(disp))
    parallax_p95 = float(np.percentile(disp, 95))
    w_img, h_img = _clip_size(clip)
    coverage = _quadrant_coverage(np.vstack([pts1, pts2]), w_img, h_img)

    # Radiale Skalierung (r2/r1)
    cx, cy = w_img*0.5, h_img*0.5
    r1 = np.linalg.norm(pts1 - np.array([cx, cy]), axis=1)
    r2 = np.linalg.norm(pts2 - np.array([cx, cy]), axis=1)
    with np.errstate(divide='ignore', invalid='ignore'):
        ratios = np.where(r1>1e-6, r2/np.maximum(r1,1e-6), 1.0)
    ratios = ratios[np.isfinite(ratios)]
    scale_median = float(np.median(ratios)) if ratios.size>0 else 1.0
    # 0..1-Normierung um 1.0 herum (±20% → 1.0)
    scale_norm = float(min(1.0, max(0.0, abs(scale_median-1.0)/0.2))) if np.isfinite(scale_median) else 0.0

    # RANSAC F
    F, inlier_mask = _ransac_F(pts1, pts2, iters=ransac_iters, thresh=ransac_thresh_px)
    inl_cnt = int(inlier_mask.sum()) if inlier_mask is not None else 0
    tot_cnt = int(len(pts1))

    if F is None or inl_cnt < 8:
        met = PreSolveMetrics(
            frame_a=int(frame_a), frame_b=int(frame_b),
            inliers=inl_cnt, total=tot_cnt,
            median_sampson_px=float('inf'), mean_sampson_px=float('inf'),
            parallax_median_px=parallax_med, parallax_p95_px=parallax_p95,
            coverage_quadrants=coverage, degenerate=True,
            F=F if return_F_and_mask else None,
            inlier_mask=inlier_mask if return_F_and_mask else None,
            inlier_ratio=(inl_cnt/max(tot_cnt,1)) if tot_cnt>0 else 0.0,
            coverage_area=_coverage_area(np.vstack([pts1, pts2]), w_img, h_img),
            quality_score=0.0, predicted_error=float('inf'),
            hom_inliers=None, hom_ratio=None,
            epipole1_in_image=None, epipole2_in_image=None,
            scale_median=scale_median, scale_norm=scale_norm,
            variant=variant or 'default', fallback_attempt=0,
            reject_reason='F_failed', root_cause='low_inliers',
        )
        if debug: _print_metric_summary(met)
        return met

    # Residuen/Sampson
    sampson = _sampson_dist(F, pts1[inlier_mask], pts2[inlier_mask])
    median_s = float(np.median(sampson)) if sampson.size>0 else float('inf')
    mean_s = float(np.mean(sampson)) if sampson.size>0 else float('inf')

    # Zusatzmetriken
    diag = float(np.hypot(w_img, h_img)) if (w_img and h_img) else 1.0
    parallax_norm = max(0.0, min(1.0, parallax_med/diag))
    parallax_rms_norm = _parallax_rms_norm(pts1, pts2, inlier_mask, diag)
    inlier_ratio = float(inl_cnt/max(tot_cnt,1))
    coverage_area = _coverage_area(np.vstack([pts1, pts2]), w_img, h_img)
    coverage_score = max(0.0, min(1.0, coverage_area * coverage))

    # Konditionszahl
    try:
        _, svals, _ = np.linalg.svd(F)
        cond_ratio = float(svals[1] / max(svals[2], 1e-12)) if len(svals)>=3 else float('inf')
    except Exception:
        cond_ratio = float('inf')
    deg_penalty = min(cond_ratio/50.0, 1.0) if np.isfinite(cond_ratio) else 1.0

    # Homographie-RANSAC
    H, h_mask = _ransac_H(pts1, pts2, iters=500, thresh=max(ransac_thresh_px, 4.0))
    hom_inliers = int(np.sum(h_mask)) if h_mask is not None else 0
    hom_ratio = float(hom_inliers/max(inl_cnt,1)) if inl_cnt>0 else None

    # Epipole
    epi1, epi2 = _epipoles(F)
    e1_in = _epipole_in_image(epi1, w_img, h_img)
    e2_in = _epipole_in_image(epi2, w_img, h_img)

    # Qualität & Fehlerprognose
    inlier_norm = 1.0 - float(np.exp(-max(inlier_ratio,0.0)*5.0))
    track_len_norm = 1.0  # optional: mit echten Track-Längen verfeinern
    combined_quality = float(inlier_norm * max(parallax_norm,1e-6) * max(coverage_score,1e-6) * track_len_norm)
    combined_quality = max(0.0, min(1.0, combined_quality))
    quality_score = (
        0.4*inlier_ratio + 0.3*parallax_norm + 0.2*coverage_score + 0.1*track_len_norm
    )
    quality_score = max(0.0, min(1.0, quality_score))

    hr = 1.0 + float(hom_ratio) if (hom_ratio is not None and np.isfinite(hom_ratio)) else 1.0
    denom = max(inlier_ratio,1e-6)*max(parallax_rms_norm,1e-6)*max(coverage_score,1e-6)*max(track_len_norm,1e-6)*(1.0+scale_norm)
    predicted_error = (median_s * (1.0 + deg_penalty) * hr) / denom if np.isfinite(median_s) else float('inf')

    # Root-Cause bestimmen
    root, reason = _root_cause(
        inl_cnt, parallax_norm, cond_ratio, hom_ratio, e1_in, e2_in, coverage_score
    )

    met = PreSolveMetrics(
        frame_a=int(frame_a), frame_b=int(frame_b),
        inliers=inl_cnt, total=tot_cnt,
        median_sampson_px=median_s, mean_sampson_px=mean_s,
        parallax_median_px=parallax_med, parallax_p95_px=parallax_p95,
        coverage_quadrants=coverage, degenerate=(root!='ok'),
        F=F if return_F_and_mask else None,
        inlier_mask=inlier_mask if return_F_and_mask else None,
        inlier_ratio=inlier_ratio, coverage_area=coverage_area,
        quality_score=quality_score, predicted_error=predicted_error,
        hom_inliers=hom_inliers, hom_ratio=hom_ratio,
        epipole1_in_image=e1_in, epipole2_in_image=e2_in,
        scale_median=scale_median, scale_norm=scale_norm,
        variant=variant or 'default', fallback_attempt=0,
        reject_reason=reason if (root!='ok') else None,
        root_cause=root,
    )
    if debug: _print_metric_summary(met)
    return met


def estimate_pre_solve_with_fallback(
    clip: bpy.types.MovieClip,
    frame_a: int,
    frame_b: int,
    *,
    ransac_thresh_px: float = 1.5,
    ransac_iters: int = 1000,
    min_track_len: int = 5,
    debug: bool = False,
) -> PreSolveMetrics:
    """Probiert mehrere Varianten durch, bis ein nicht-degenerates Ergebnis entsteht."""
    variants = [
        ("default", dict(ransac_thresh_px=ransac_thresh_px, ransac_iters=ransac_iters, min_track_len=min_track_len)),
        ("loose_thresh", dict(ransac_thresh_px=max(6.0, ransac_thresh_px*2), ransac_iters=ransac_iters, min_track_len=min_track_len)),
        ("short_tracks", dict(ransac_thresh_px=max(6.0, ransac_thresh_px*2), ransac_iters=ransac_iters, min_track_len=max(3, min_track_len//2))),
    ]
    last = None
    for i,(name,kw) in enumerate(variants):
        m = estimate_pre_solve_metrics(
            clip, frame_a, frame_b,
            variant=name, debug=debug,
            **kw
        )
        m.fallback_attempt = i
        if not m.degenerate and np.isfinite(m.predicted_error or np.inf):
            return m
        last = m
    return last  # alles degenerate – letztes Ergebnis zurück


# =============================
# Interna (Geometrie & Tracking)
# =============================

def _clip_size(clip: bpy.types.MovieClip) -> Tuple[int, int]:
    w, h = clip.size
    return int(w), int(h)


def _to_pixels(pt: Tuple[float, float], w: int, h: int) -> np.ndarray:
    return np.array([pt[0] * w, pt[1] * h], dtype=np.float64)

def _gather_tracks_for_frames(
    clip: bpy.types.MovieClip,
    f1: int,
    f2: int,
    *,
    min_length: int = 5,
    require_continuous: bool = False,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], List[bpy.types.MovieTrackingTrack]]:
    w, h = _clip_size(clip)
    pts1, pts2, used_tracks = [], [], []
    for tr in clip.tracking.tracks:
        if len(tr.markers) < min_length or getattr(tr, "mute", False):
            continue
        m1 = tr.markers.find_frame(f1)
        m2 = tr.markers.find_frame(f2)
        if not m1 or not m2 or getattr(m1, "mute", False) or getattr(m2, "mute", False):
            continue
        if require_continuous and not _markers_continuous_between(tr, f1, f2):
            continue
        pts1.append(_to_pixels(m1.co, w, h))
        pts2.append(_to_pixels(m2.co, w, h))
        used_tracks.append(tr)
    if not pts1:
        return None, None, []
    return np.vstack(pts1), np.vstack(pts2), used_tracks


def _markers_continuous_between(tr: bpy.types.MovieTrackingTrack, f1: int, f2: int) -> bool:
    if getattr(tr, "mute", False):
        return False
    if f2 < f1:
        f1, f2 = f2, f1
    m_by_frame = {m.frame: m for m in tr.markers if not getattr(m, "mute", False)}
    for f in range(f1, f2 + 1):
        if f not in m_by_frame:
            return False
    return True


def _normalize_points(pts: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mean = np.mean(pts, axis=0)
    scale = np.sqrt(2) / max(np.mean(np.linalg.norm(pts - mean, axis=1)), 1e-12)
    T = np.array([[scale, 0.0, -scale*mean[0]],[0.0, scale, -scale*mean[1]],[0.0,0.0,1.0]], dtype=np.float64)
    pts_h = np.column_stack([pts, np.ones(len(pts))])
    npts = (T @ pts_h.T).T[:, :2]
    return npts, T


def _eight_point_F(p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    n = p1.shape[0]
    A = np.zeros((n, 9), dtype=np.float64)
    x, y = p1[:, 0], p1[:, 1]
    x2, y2 = p2[:, 0], p2[:, 1]
    A[:, 0] = x2 * x; A[:, 1] = x2 * y; A[:, 2] = x2
    A[:, 3] = y2 * x; A[:, 4] = y2 * y; A[:, 5] = y2
    A[:, 6] = x;     A[:, 7] = y;      A[:, 8] = 1.0
    _, _, Vt = np.linalg.svd(A)
    F = Vt[-1].reshape(3, 3)
    U, S, Vt = np.linalg.svd(F)
    S[-1] = 0.0
    return U @ np.diag(S) @ Vt


def _sampson_dist(F: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    p1h = np.column_stack([p1, np.ones(len(p1))])
    p2h = np.column_stack([p2, np.ones(len(p2))])
    Fx1 = (F @ p1h.T).T
    Ftx2 = (F.T @ p2h.T).T
    x2tFx1 = np.sum(p2h * (F @ p1h.T).T, axis=1)
    denom = Fx1[:,0]**2 + Fx1[:,1]**2 + Ftx2[:,0]**2 + Ftx2[:,1]**2
    d2 = (x2tFx1**2) / (denom + 1e-12)
    return np.sqrt(d2)


def _ransac_F(
    p1: np.ndarray,
    p2: np.ndarray,
    *,
    iters: int = 1000,
    thresh: float = 1.5,
    seed: int = 42,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    n = len(p1)
    if n < 8:
        return None, None
    rng = np.random.default_rng(seed)
    best_inliers: Optional[np.ndarray] = None
    best_F: Optional[np.ndarray] = None
    n1, T1 = _normalize_points(p1)
    n2, T2 = _normalize_points(p2)
    for _ in range(max(1, iters)):
        idx = rng.choice(n, 8, replace=False)
        F_n = _eight_point_F(n1[idx], n2[idx])
        F = T2.T @ F_n @ T1.T
        d = _sampson_dist(F, p1, p2)
        inl = d < thresh
        if best_inliers is None or inl.sum() > best_inliers.sum():
            best_inliers = inl; best_F = F
    if best_inliers is None or best_inliers.sum() < 8:
        return None, best_inliers
    n1_in, T1 = _normalize_points(p1[best_inliers])
    n2_in, T2 = _normalize_points(p2[best_inliers])
    F_n = _eight_point_F(n1_in, n2_in)
    F = T2.T @ F_n @ T1.T
    return F, best_inliers


def _compute_homography(p1: np.ndarray, p2: np.ndarray) -> Optional[np.ndarray]:
    n = p1.shape[0]
    if n < 4:
        return None
    A = []
    for i in range(n):
        x, y = float(p1[i,0]), float(p1[i,1])
        xp, yp = float(p2[i,0]), float(p2[i,1])
        A.append([0,0,0, -x,-y,-1, yp*x, yp*y, yp])
        A.append([x,y,1, 0,0,0, -xp*x, -xp*y, -xp])
    A = np.asarray(A, dtype=np.float64)
    try:
        _, _, Vt = np.linalg.svd(A)
        H = Vt[-1, :].reshape(3,3)
        if abs(H[2,2])>1e-12:
            H = H / H[2,2]
        return H
    except Exception:
        return None


def _transform_points_homography(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts_h = np.column_stack([pts, np.ones(len(pts))])
    tp = (H @ pts_h.T).T
    w = tp[:, 2:3]
    w[w==0.0] = 1e-12
    return tp[:, :2] / w


def _ransac_H(
    p1: np.ndarray,
    p2: np.ndarray,
    *,
    iters: int = 500,
    thresh: float = 4.0,
    seed: int = 42,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    n = len(p1)
    if n < 4:
        return None, None
    rng = np.random.default_rng(seed)
    best_H = None
    best_mask = None
    best_count = 0
    for _ in range(max(1, iters)):
        try:
            idx = rng.choice(n, 4, replace=False)
        except Exception:
            continue
        H = _compute_homography(p1[idx], p2[idx])
        if H is None:
            continue
        proj = _transform_points_homography(H, p1)
        err = np.linalg.norm(proj - p2, axis=1)
        mask = err < thresh
        count = int(np.sum(mask))
        if count > best_count:
            best_count = count; best_mask = mask; best_H = H
    if best_H is None or best_mask is None or best_count < 4:
        return None, best_mask
    try:
        H_refit = _compute_homography(p1[best_mask], p2[best_mask])
        return H_refit, best_mask
    except Exception:
        return best_H, best_mask


def _parallax_rms_norm(pts1, pts2, inlier_mask, diag: float) -> float:
    try:
        vecs = (pts2[inlier_mask] - pts1[inlier_mask]) if (pts1 is not None and pts2 is not None and inlier_mask is not None) else (pts2 - pts1)
        if vecs is not None and len(vecs) > 0:
            mean_vec = np.mean(vecs, axis=0)
            resid = vecs - mean_vec
            rms = float(np.sqrt(np.mean(np.sum(resid**2, axis=1))))
        else:
            rms = 0.0
    except Exception:
        rms = 0.0
    v = rms / diag if diag>0 else 0.0
    return max(0.0, min(1.0, v))


def _coverage_area(all_pts: np.ndarray, w: int, h: int) -> float:
    if all_pts.size == 0:
        return 0.0
    min_x, min_y = np.min(all_pts, axis=0)
    max_x, max_y = np.max(all_pts, axis=0)
    bb_w = max(0.0, (max_x - min_x) / float(w))
    bb_h = max(0.0, (max_y - min_y) / float(h))
    return float(max(0.0, bb_w) * max(0.0, bb_h))


def _epipoles(F: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    try:
        U,S,Vt = np.linalg.svd(F)
        e1 = Vt[-1, :]  # rechte Nullraum: F * e1 = 0
        e2 = U[:, -1]   # linke Nullraum: e2^T * F = 0
        return e1, e2
    except Exception:
        return None, None


def _epipole_in_image(e: Optional[np.ndarray], w: int, h: int, margin: float=0.0) -> Optional[bool]:
    if e is None or abs(e[-1]) < 1e-12:
        return None
    ex, ey = e[0]/e[2], e[1]/e[2]
    return ( -margin <= ex <= w+margin ) and ( -margin <= ey <= h+margin )


# =============================
# Debug/Analyse/Export
# =============================

def _print_metric_summary(m: PreSolveMetrics) -> None:
    try:
        var = m.variant or 'default'
        deg = 'DEGEN' if m.degenerate else 'OK'
        inlr = f"{m.inliers}/{m.total}"
        ms = f"{m.median_sampson_px:.3f}" if np.isfinite(m.median_sampson_px) else 'inf'
        q = f"q={m.quality_score:.2f}" if m.quality_score is not None else "q=?"
        pe = f"pred={m.predicted_error:.2f}" if (m.predicted_error is not None and np.isfinite(m.predicted_error)) else "pred=inf"
        par = f"par={m.parallax_median_px:.2f}"
        sca = f"scale={m.scale_median:.3f}" if m.scale_median is not None else "scale=?"
        hrat = f"h/F={m.hom_ratio:.2f}" if m.hom_ratio is not None else "h/F=?"
        epi = f"epi({m.epipole1_in_image},{m.epipole2_in_image})"
        rc = m.root_cause or "?"
        print(f"[Preflight] {deg} {var} f=({m.frame_a},{m.frame_b}) {inlr} sampson={ms} {q} {pe} {par} {sca} cov={m.coverage_quadrants:.2f} {hrat} {epi} cause={rc}")
    except Exception as ex:
        print(f"[Preflight] summary failed: {ex!r}")


def export_preflight_report_csv(metrics: Sequence[PreSolveMetrics], filepath: Optional[str]=None) -> str:
    if filepath is None:
        import os
        tmp = bpy.app.tempdir if hasattr(bpy.app, 'tempdir') else '/tmp/'
        filepath = os.path.join(tmp, 'preflight_report.csv')
    import csv
    with open(filepath, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['frame_a','frame_b','inliers','total','median_sampson','parallax_med','coverage','degenerate','inlier_ratio','quality','pred_error','hom_ratio','scale_median','epipole1_in','epipole2_in','variant','fallback','root_cause','reject_reason'])
        for m in metrics:
            w.writerow([
                m.frame_a, m.frame_b, m.inliers, m.total, m.median_sampson_px,
                m.parallax_median_px, m.coverage_quadrants, int(bool(m.degenerate)),
                m.inlier_ratio, m.quality_score, m.predicted_error, m.hom_ratio,
                m.scale_median, m.epipole1_in_image, m.epipole2_in_image,
                m.variant, m.fallback_attempt, m.root_cause, m.reject_reason
            ])
    print(f"[Preflight] Report exportiert → {filepath}")
    return filepath


def _root_cause(inliers: int, parallax_norm: float, cond_ratio: float, hom_ratio: Optional[float], e1_in: Optional[bool], e2_in: Optional[bool], coverage_score: float) -> Tuple[str,str]:
    # heuristik
    if inliers < 8:
        return 'low_inliers', 'too_few_inliers'
    if parallax_norm < 0.005 and (hom_ratio is None or hom_ratio > 0.8):
        return 'planar_or_forward', 'low_parallax_high_homography'
    if not np.isfinite(cond_ratio) or cond_ratio > 50.0:
        return 'ill_conditioned_F', 'bad_condition_number'
    if coverage_score < 0.1:
        return 'poor_coverage', 'points_too_clustered'
    # Epipole im Bild (typisch Vorwärts/ Rückwärts) → nur Hinweis
    if e1_in is True or e2_in is True:
        return 'ok', 'epipole_in_frame_hint'
    return 'ok', ''


# =============================
# Beispiel (nur Doku)
# =============================
if False:  # pragma: no cover
    clip = bpy.context.edit_movieclip
    # Schnellscan mit Fallback und Logging
    res = scan_scene(clip, deltas=(8,12,16,24,32), stride=10, use_fallback=True, debug=True)
    export_preflight_report_csv(res)
