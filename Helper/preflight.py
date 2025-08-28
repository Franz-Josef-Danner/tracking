"""Preflight-Helper für Blender-Tracking

Reiner Helfer (ohne UI/Operatoren), der für ein Frame-Paar aus einem
MovieClip robuste 2D-Geometriemetriken berechnet, die mit dem späteren
Reprojektionserror korrelieren. Ideal als Vorprüfung vor dem Solve.

Funktionen:
- estimate_pre_solve_metrics(clip, frame_a, frame_b, ...): Dict mit Kennzahlen
- scan_frame_pairs(clip, pairs, ...): mehrere Paare auf einmal, aggregiert

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

    # RANSAC/Fundamental
    inliers: int
    total: int
    median_sampson_px: float
    mean_sampson_px: float

    # Parallax & Abdeckung
    parallax_median_px: float
    parallax_p95_px: float
    coverage_quadrants: float  # 0..1

    # Diagnosen
    degenerate: bool  # z. B. reine Rotation / zu wenig Parallax / <8 Inlier

    # Optional: für weiterführende Auswertung
    F: Optional[np.ndarray] = None
    inlier_mask: Optional[np.ndarray] = None

    def as_dict(self) -> Dict:
        d = asdict(self)
        # Arrays für SerDes entfernen/vereinfachen (Syntaxfix)
        if isinstance(d.get("F"), np.ndarray):
            d["F"] = d["F"].tolist()
        if isinstance(d.get("inlier_mask"), np.ndarray):
            d["inlier_mask"] = d["inlier_mask"].astype(bool).tolist()
        return d


# =============================
# Public API
# =============================

def _markers_continuous_between(tr: bpy.types.MovieTrackingTrack, f1: int, f2: int) -> bool:
    """True, wenn zwischen f1..f2 lückenlos Marker existieren (keine Gaps),
    und weder Track noch Marker gemutet sind."""
    if getattr(tr, "mute", False):
        return False
    if f2 < f1:
        f1, f2 = f2, f1

    # Map: frame -> marker (nur ungemutet)
    m_by_frame = {m.frame: m for m in tr.markers if not getattr(m, "mute", False)}

    # lückenlos?
    for f in range(f1, f2 + 1):
        if f not in m_by_frame:
            return False
    return True


# --- NEU: Helfer für Frame-Mapping Szene -> Clip/Marker ----------------------
def _scene_to_clip_frame(clip: bpy.types.MovieClip, f_scene: int) -> int:
    """Mappt einen Szenen-Frame auf den Marker/Clip-Frame.
    Nutzt clip.frame_start als Offset (Blenders MovieClip-Start im Szenenkontext).
    Annahme: Marker starten typischerweise bei 1.
    """
    start = int(getattr(clip, "frame_start", 1))
    return int(f_scene - start + 1)

# --- PATCH: scan_scene erzeugt Paare in Szenen-Frames, mapped dann sauber ----
def scan_scene(
    clip: Optional[bpy.types.MovieClip] = None,
    *,
    step: int = 10,
    ransac_thresh_px: float = 1.5,
    ransac_iters: int = 1000,
    min_track_len: int = 5,
) -> List[PreSolveMetrics]:
    if step <= 0:
        raise ValueError("step muss > 0 sein")
    if clip is None:
        clip = bpy.context.edit_movieclip
    if clip is None:
        raise RuntimeError("Kein aktiver MovieClip im Kontext.")

    scene = bpy.context.scene
    s_start = int(scene.frame_start)
    s_end = int(scene.frame_end)

    # Scene-Frame-Paare erzeugen – NICHT in Clip/Marker-Frames mappen!
    pairs: List[Tuple[int, int]] = [(f, f + step) for f in range(s_start, s_end - step + 1, step)]

    return scan_frame_pairs(
        clip,
        pairs,
        ransac_thresh_px=ransac_thresh_px,
        ransac_iters=ransac_iters,
        min_track_len=min_track_len,
    )


# --- PATCH: estimate_pre_solve_metrics nutzt Marker-Frames -------------------
def estimate_pre_solve_metrics(
    clip: bpy.types.MovieClip,
    frame_a: int,
    frame_b: int,
    *,
    ransac_thresh_px: float = 1.5,
    ransac_iters: int = 1000,
    min_track_len: int = 5,
    return_F_and_mask: bool = False,
) -> PreSolveMetrics:
    """Berechnet Pre-Solve-Kennzahlen für ein Frame-Paar."""

    def _try(fa: int, fb: int):
        return _gather_tracks_for_frames(clip, fa, fb, min_length=min_track_len)

    # 1) Direkt mit Scene-Frames versuchen
    pts1, pts2, tracks = _try(int(frame_a), int(frame_b))

    # 2) Fallback #1: Offsetting über clip.frame_start (üblich)
    if (pts1 is None or (len(pts1) < 8)) and hasattr(clip, "frame_start"):
        off = int(getattr(clip, "frame_start", 1)) - 1
        pts1, pts2, tracks = _try(int(frame_a) - off, int(frame_b) - off)

    # 3) Fallback #2: an Marker-Domäne der vorhandenen Tracks ausrichten
    if pts1 is None or len(pts1) < 8:
        all_tracks = [tr for tr in clip.tracking.tracks if len(tr.markers) > 0]
        if all_tracks:
            c_min = min(tr.markers[0].frame for tr in all_tracks)
            s_start = int(bpy.context.scene.frame_start)
            off2 = s_start - c_min
            pts1, pts2, tracks = _try(int(frame_a) - off2, int(frame_b) - off2)

    if pts1 is None or len(pts1) < 8:
        return PreSolveMetrics(
            frame_a=int(frame_a),
            frame_b=int(frame_b),
            inliers=0,
            total=0 if pts1 is None else int(len(pts1)),
            median_sampson_px=float("inf"),
            mean_sampson_px=float("inf"),
            parallax_median_px=0.0,
            parallax_p95_px=0.0,
            coverage_quadrants=0.0,
            degenerate=True,
            F=None,
            inlier_mask=None,
        )

    # Parallax & Coverage (auf allen Kandidaten)
    disp = np.linalg.norm(pts2 - pts1, axis=1)
    parallax_med = float(np.median(disp))
    parallax_p95 = float(np.percentile(disp, 95))
    coverage = _quadrant_coverage(np.vstack([pts1, pts2]), *_clip_size(clip))

    # RANSAC + Refit
    F, inlier_mask = _ransac_F(pts1, pts2, iters=ransac_iters, thresh=ransac_thresh_px)

    if F is None or inlier_mask.sum() < 8:
        return PreSolveMetrics(
            frame_a=int(frame_a),
            frame_b=int(frame_b),
            inliers=0 if inlier_mask is None else int(inlier_mask.sum()),
            total=int(len(pts1)),
            median_sampson_px=float("inf"),
            mean_sampson_px=float("inf"),
            parallax_median_px=parallax_med,
            parallax_p95_px=parallax_p95,
            coverage_quadrants=coverage,
            degenerate=True,
            F=F if return_F_and_mask else None,
            inlier_mask=inlier_mask if return_F_and_mask else None,
        )

    sampson = _sampson_dist(F, pts1[inlier_mask], pts2[inlier_mask])
    return PreSolveMetrics(
        frame_a=int(frame_a),
        frame_b=int(frame_b),
        inliers=int(inlier_mask.sum()),
        total=int(len(inlier_mask)),
        median_sampson_px=float(np.median(sampson)),
        mean_sampson_px=float(np.mean(sampson)),
        parallax_median_px=parallax_med,
        parallax_p95_px=parallax_p95,
        coverage_quadrants=coverage,
        degenerate=False,
        F=F if return_F_and_mask else None,
        inlier_mask=inlier_mask if return_F_and_mask else None,
    )



def scan_frame_pairs(
    clip: bpy.types.MovieClip,
    pairs: Sequence[Tuple[int, int]],
    *,
    ransac_thresh_px: float = 1.5,
    ransac_iters: int = 1000,
    min_track_len: int = 5,
) -> List[PreSolveMetrics]:
    """Batch-Auswertung mehrerer Frame-Paare."""
    results: List[PreSolveMetrics] = []
    for a, b in pairs:
        results.append(
            estimate_pre_solve_metrics(
                clip,
                a,
                b,
                ransac_thresh_px=ransac_thresh_px,
                ransac_iters=ransac_iters,
                min_track_len=min_track_len,
            )
        )
    return results


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
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], List[bpy.types.MovieTrackingTrack]]:
    w, h = _clip_size(clip)
    pts1: List[np.ndarray] = []
    pts2: List[np.ndarray] = []
    used_tracks: List[bpy.types.MovieTrackingTrack] = []

    for tr in clip.tracking.tracks:
        if len(tr.markers) < min_length or getattr(tr, "mute", False):
            continue
        m1 = tr.markers.find_frame(f1)
        m2 = tr.markers.find_frame(f2)
        if not m1 or not m2:
            continue
        if getattr(m1, "mute", False) or getattr(m2, "mute", False):
            continue
        # Track muss das Intervall wirklich ABDECKEN (keine segment-Gaps)
        if not _markers_continuous_between(tr, f1, f2):
            continue

        pts1.append(_to_pixels(m1.co, w, h))
        pts2.append(_to_pixels(m2.co, w, h))
        used_tracks.append(tr)

    if not pts1:
        return None, None, []
    return np.vstack(pts1), np.vstack(pts2), used_tracks



def _normalize_points(pts: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Hartley-Normalisierung (mean->0, mean distance->sqrt(2))."""
    mean = np.mean(pts, axis=0)
    scale = np.sqrt(2) / max(np.mean(np.linalg.norm(pts - mean, axis=1)), 1e-12)
    T = np.array(
        [[scale, 0.0, -scale * mean[0]], [0.0, scale, -scale * mean[1]], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    pts_h = np.column_stack([pts, np.ones(len(pts))])
    npts = (T @ pts_h.T).T[:, :2]
    return npts, T


def _eight_point_F(p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    """Linearer 8-Point-Solver (Inputs: normalisierte 2D-Paare)."""
    n = p1.shape[0]
    A = np.zeros((n, 9), dtype=np.float64)
    x, y = p1[:, 0], p1[:, 1]
    x2, y2 = p2[:, 0], p2[:, 1]
    A[:, 0] = x2 * x
    A[:, 1] = x2 * y
    A[:, 2] = x2
    A[:, 3] = y2 * x
    A[:, 4] = y2 * y
    A[:, 5] = y2
    A[:, 6] = x
    A[:, 7] = y
    A[:, 8] = 1.0

    _, _, Vt = np.linalg.svd(A)
    F = Vt[-1].reshape(3, 3)

    # Rang-2-Zwang
    U, S, Vt = np.linalg.svd(F)
    S[-1] = 0.0
    F = U @ np.diag(S) @ Vt
    return F


def _sampson_dist(F: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    """Sampson-Distanz (Pixel)."""
    p1h = np.column_stack([p1, np.ones(len(p1))])
    p2h = np.column_stack([p2, np.ones(len(p2))])

    Fx1 = (F @ p1h.T).T
    Ftx2 = (F.T @ p2h.T).T
    x2tFx1 = np.sum(p2h * (F @ p1h.T).T, axis=1)

    denom = Fx1[:, 0] ** 2 + Fx1[:, 1] ** 2 + Ftx2[:, 0] ** 2 + Ftx2[:, 1] ** 2
    d2 = (x2tFx1 ** 2) / (denom + 1e-12)
    return np.sqrt(d2)


def _ransac_F(
    p1: np.ndarray,
    p2: np.ndarray,
    *,
    iters: int = 1000,
    thresh: float = 1.5,
    seed: int = 42,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Einfaches RANSAC zur F-Schätzung in Pixelkoordinaten.

    Returns:
        (F, inlier_mask)
    """
    n = len(p1)
    if n < 8:
        return None, None

    rng = np.random.default_rng(seed)

    best_inliers: Optional[np.ndarray] = None
    best_F: Optional[np.ndarray] = None

    # Global normalisieren (Robustheit)
    n1, T1 = _normalize_points(p1)
    n2, T2 = _normalize_points(p2)

    for _ in range(max(1, iters)):
        idx = rng.choice(n, 8, replace=False)
        F_n = _eight_point_F(n1[idx], n2[idx])
        F = T2.T @ F_n @ T1.T  # zurück-denormalisieren

        d = _sampson_dist(F, p1, p2)
        inl = d < thresh
        if best_inliers is None or inl.sum() > best_inliers.sum():
            best_inliers = inl
            best_F = F

    if best_inliers is None or best_inliers.sum() < 8:
        return None, best_inliers

    # Refit auf allen Inliern
    n1_in, T1 = _normalize_points(p1[best_inliers])
    n2_in, T2 = _normalize_points(p2[best_inliers])
    F_n = _eight_point_F(n1_in, n2_in)
    F = T2.T @ F_n @ T1.T

    return F, best_inliers


def _quadrant_coverage(pts: np.ndarray, w: int, h: int) -> float:
    cx, cy = w * 0.5, h * 0.5
    q = [(p[0] > cx, p[1] > cy) for p in pts]
    return len(set(q)) / 4.0


# =============================
# Komfort-Helfer
# =============================

def worst_tracks_by_residual(
    clip: bpy.types.MovieClip,
    frame_a: int,
    frame_b: int,
    *,
    top_k: int = 10,
    ransac_thresh_px: float = 1.5,
    min_track_len: int = 5,
) -> List[Tuple[bpy.types.MovieTrackingTrack, float]]:
    """Gibt die schlechtesten Tracks (höchste Sampson-Residuals) zurück.

    Nützlich, um vor dem Solve gezielt zu deaktivieren.
    """
    pts1, pts2, tracks = _gather_tracks_for_frames(
        clip, frame_a, frame_b, min_length=min_track_len
    )
    if pts1 is None or len(pts1) < 8:
        return []

    F, inlier_mask = _ransac_F(pts1, pts2, thresh=ransac_thresh_px)
    if F is None or inlier_mask is None:
        return []

    # Residuen auf allen korrespondierenden Punkten (nicht nur Inlier)
    residuals = _sampson_dist(F, pts1, pts2)
    order = np.argsort(residuals)[::-1]  # absteigend
    out: List[Tuple[bpy.types.MovieTrackingTrack, float]] = []
    for idx in order[:top_k]:
        out.append((tracks[idx], float(residuals[idx])))
    return out


# =============================
# Beispiel (nur Doku, wird nicht automatisch ausgeführt)
# =============================
if False:  # pragma: no cover
    # Anwendung in der Blender-Python-Konsole:
    clip = bpy.context.edit_movieclip
    met = estimate_pre_solve_metrics(clip, 101, 130)
    print(met)

    # Mehrere Paare scannen
    pairs = [(100, 120), (100, 140), (110, 160)]
    results = scan_frame_pairs(clip, pairs)
    for r in results:
        print(r.frame_a, r.frame_b, r.median_sampson_px, r.parallax_median_px)

    # Schlechteste Tracks listen
    bad = worst_tracks_by_residual(clip, 101, 130, top_k=5)
    for tr, res in bad:
        print(tr.name, res)
