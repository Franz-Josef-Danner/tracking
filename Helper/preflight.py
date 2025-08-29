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
    """Ergebniscontainer für die Preflight-Messung eines Frame-Paars.

    Neben klassischen RANSAC- und Parallaxwerten werden hier zusätzliche
    Qualitätsmerkmale hinterlegt, um eine robustere Prognose des späteren
    Solve-Fehlers zu ermöglichen. Alle zusätzlichen Metriken sind optional
    und werden mit sinnvollen Defaultwerten initialisiert, um die
    Abwärtskompatibilität zu wahren.
    """

    # Basisangaben des betrachteten Frame-Paars
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

    # Erweiterte Metriken zur Qualitätsvorhersage (alle optional)
    inlier_ratio: Optional[float] = None  # Anteil Inlier/Total
    track_count: Optional[int] = None  # Anzahl verwendeter Tracks
    avg_track_length: Optional[float] = None  # Durchschnittliche Track-Länge
    median_track_length: Optional[float] = None  # Median der Track-Längen
    coverage_area: Optional[float] = None  # Normierte Bounding-Box-Fläche der Punkte
    quality_score: Optional[float] = None  # 0..1; höher = bessere Geometrie
    predicted_error: Optional[float] = None  # Grobe Schätzung des späteren Solve-Fehlers

    # Radiale Skalierung (bei Vorwärts-/Rückwärtsfahrt)
    # scale_median: medianes Verhältnis der radialen Abstände (r2/r1) der Punkte zum Bildzentrum.
    # scale_norm: normierte Skalierung 0..1 (0 = keine Skalierung, 1 = starke Skalierung). Wird bei
    #             minimaler Parallaxe als zusätzlicher Qualitätsfaktor herangezogen.
    scale_median: Optional[float] = None
    scale_norm: Optional[float] = None

    # Optional: Inlier-Anzahl und Verhältnis der Homographie-Schätzung
    hom_inliers: Optional[int] = None  # Anzahl der Homographie-Inlier
    hom_ratio: Optional[float] = None  # Verhältnis H-Inlier/F-Inlier (1 == degeneriert)

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
    step: int = 100,
    ransac_thresh_px: float = 8,
    ransac_iters: int = 1000,
    min_track_len: int = 5,
) -> List[PreSolveMetrics]:
    if step <= 0:
        raise ValueError("step muss > 0 sein")
    if clip is None:
        clip = bpy.context.edit_movieclip
        a, b = 1, 11  # dein Paar
        pts1, pts2, tracks = _gather_tracks_for_frames(clip, a, b, min_length=5)
        print("kandidaten =", 0 if pts1 is None else len(pts1))
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
        # Fallback-Paar ohne ausreichende Punkte. Setze alle Metriken auf
        # Standardwerte, kennzeichne als degeneriert.
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
            inlier_ratio=0.0,
            track_count=0,
            avg_track_length=0.0,
            median_track_length=0.0,
            coverage_area=0.0,
            quality_score=0.0,
            predicted_error=float("inf"),
            hom_inliers=None,
            hom_ratio=None,
            scale_median=None,
            scale_norm=None,
        )

    # Parallax & Coverage (auf allen Kandidaten)
    disp = np.linalg.norm(pts2 - pts1, axis=1)
    parallax_med = float(np.median(disp))
    parallax_p95 = float(np.percentile(disp, 95))
    coverage = _quadrant_coverage(np.vstack([pts1, pts2]), *_clip_size(clip))

    # ----------------------------------------------
    # Radiale Skalierung: Für reine Vorwärtsfahrt ändert sich der
    # Abstand der Punkte zum Bildzentrum. Wir nutzen diese Skalierung
    # zur Stabilisierung der Qualitätsbewertung bei geringer Parallaxe.
    try:
        w_img, h_img = _clip_size(clip)
        cx, cy = w_img * 0.5, h_img * 0.5
        # Abstände der Punkte zum Zentrum
        rad1 = np.linalg.norm(pts1 - np.array([[cx, cy]]), axis=1)
        rad2 = np.linalg.norm(pts2 - np.array([[cx, cy]]), axis=1)
        # Verhältnisse r2/r1 (Vergrößerung >1 bei Vorwärtsfahrt)
        # vermeide Division durch Null bzw. sehr kleine Werte
        ratios = rad2 / np.maximum(rad1, 1e-3)
        # Filtere ungültige Werte
        ratios = ratios[np.isfinite(ratios)]
        if ratios.size > 0:
            scale_median = float(np.median(ratios))
        else:
            scale_median = 1.0
        # Normierung: Abweichung vom 1.0 (keine Skalierung). Wir setzen eine
        # Referenz von 20% Skalierung als 1.0; kleinere Skalierungen werden
        # entsprechend linear skaliert. Negative oder zu kleine Werte werden
        # abgeschnitten.
        scale_norm = (scale_median - 1.0) / 0.2
        scale_norm = float(max(0.0, min(scale_norm, 1.0)))
    except Exception:
        scale_median = None
        scale_norm = 0.0

    # Zusätzliche Metriken vorbereiten
    # Anzahl und Länge der Tracks
    track_count = len(tracks) if tracks is not None else 0
    # Liste aller Track-Längen (Anzahl Marker pro Track)
    track_lengths = []
    if tracks:
        for tr in tracks:
            try:
                track_lengths.append(len(getattr(tr, "markers", [])))
            except Exception:
                pass
    # Durchschnitts- und Medianlänge
    avg_len = float(np.mean(track_lengths)) if track_lengths else 0.0
    med_len = float(np.median(track_lengths)) if track_lengths else 0.0
    # Normierte Bounding-Box-Fläche der Gesamtpunkte (0..1)
    w_img, h_img = _clip_size(clip)
    all_pts = np.vstack([pts1, pts2]) if pts1 is not None and pts2 is not None else np.array([])
    if all_pts.size > 0:
        min_x, min_y = np.min(all_pts, axis=0)
        max_x, max_y = np.max(all_pts, axis=0)
        bb_w = max(0.0, (max_x - min_x) / float(w_img))
        bb_h = max(0.0, (max_y - min_y) / float(h_img))
        coverage_area = float(max(0.0, bb_w) * max(0.0, bb_h))
    else:
        coverage_area = 0.0

    # RANSAC + Refit
    F, inlier_mask = _ransac_F(pts1, pts2, iters=ransac_iters, thresh=ransac_thresh_px)

    if F is None or inlier_mask.sum() < 8:
        # In diesem Fall konnte keine verlässliche Fundamentalmatrix ermittelt werden.
        inl_cnt = 0 if inlier_mask is None else int(inlier_mask.sum())
        tot_cnt = int(len(pts1)) if pts1 is not None else 0
        inlier_ratio = float(inl_cnt / tot_cnt) if tot_cnt > 0 else 0.0
        # Qualitätsabschätzung bleibt undefiniert, da das Paar degeneriert ist
        quality_score = 0.0
        predicted_error = float("inf")
        return PreSolveMetrics(
            frame_a=int(frame_a),
            frame_b=int(frame_b),
            inliers=inl_cnt,
            total=tot_cnt,
            median_sampson_px=float("inf"),
            mean_sampson_px=float("inf"),
            parallax_median_px=parallax_med,
            parallax_p95_px=parallax_p95,
            coverage_quadrants=coverage,
            degenerate=True,
            F=F if return_F_and_mask else None,
            inlier_mask=inlier_mask if return_F_and_mask else None,
            inlier_ratio=inlier_ratio,
            track_count=track_count,
            avg_track_length=avg_len,
            median_track_length=med_len,
            coverage_area=coverage_area,
            quality_score=quality_score,
            predicted_error=predicted_error,
            hom_inliers=None,
            hom_ratio=None,
            scale_median=scale_median,
            scale_norm=scale_norm,
        )

    # Berechne Sampson-Distanzen der Inlier
    sampson = _sampson_dist(F, pts1[inlier_mask], pts2[inlier_mask])
    inl_cnt = int(inlier_mask.sum())
    tot_cnt = int(len(inlier_mask))
    inlier_ratio = float(inl_cnt / tot_cnt) if tot_cnt > 0 else 0.0
    median_s = float(np.median(sampson)) if sampson.size > 0 else float("inf")
    mean_s = float(np.mean(sampson)) if sampson.size > 0 else float("inf")

    #
    # Qualitätsschätzung und erwarteter Solve-Fehler
    # ----------------------------------------------
    # Die ursprüngliche Implementierung berechnete den ``quality_score`` als
    # gewichtete Summe einiger normalisierter Faktoren und schätzte den
    # ``predicted_error`` anschließend als Quotient aus dem mittleren
    # Sampson‑Fehler und dieser Qualität. In der Praxis erwies sich dieses
    # Verfahren als instabil: Insbesondere wenn einzelne Faktoren wie
    # ``inlier_ratio`` sehr klein sind, dominiert der Quotient und die
    # Fehlerschätzung geht gegen Unendlich. Um eine robustere Prognose zu
    # erhalten, kombinieren wir jetzt mehrere Kenngrößen multiplicativ und
    # berücksichtigen zudem die Kondition der Fundamentalmatrix als
    # Degenerationsindikator. Durch eine sanfte Logistik‑Normalisierung
    # verhindern wir, dass einzelne extrem schlechte Werte die gesamte
    # Bewertung dominieren.

    # 1) Normierung der Parallaxe anhand der Bilddiagonale (0..1)
    diag = float(np.hypot(w_img, h_img)) if (w_img and h_img) else 1.0
    parallax_norm = parallax_med / diag if diag > 0.0 else 0.0
    parallax_norm = max(0.0, min(parallax_norm, 1.0))

    # --- NEU: Parallax-Score nach Keyframe-Helper --------------------------------
    # Berechne einen robusteren Parallax-Score als Wurzel des mittleren
    # Quadrats der Residuen nach Abzug der Mittelverschiebung. Diese Größe
    # korreliert mit echter räumlicher Parallaxe und ist weniger anfällig für
    # konstante Verschiebungen (z.B. Tracking-Drift). Normalisiere auf die
    # Bilddiagonale.
    try:
        # Vektoren der Punktverschiebungen (Px2)
        vecs = (pts2[inlier_mask] - pts1[inlier_mask]) if (pts1 is not None and pts2 is not None and inlier_mask is not None) else (pts2 - pts1)
        if vecs is not None and len(vecs) > 0:
            mean_vec = np.mean(vecs, axis=0)
            resid = vecs - mean_vec
            rms = float(np.sqrt(np.mean(np.sum(resid**2, axis=1))))
        else:
            rms = 0.0
    except Exception:
        rms = 0.0
    parallax_rms_norm = rms / diag if diag > 0.0 else 0.0
    parallax_rms_norm = max(0.0, min(parallax_rms_norm, 1.0))

    # 2) Normierung der Tracklängen. Wir gehen davon aus, dass 50 Frames
    #     pro Track bereits sehr gut sind (typische Länge für stabile Tracks).
    track_len_norm = avg_len / 50.0 if avg_len > 0.0 else 0.0
    track_len_norm = max(0.0, min(track_len_norm, 1.0))

    # 3) Coverage‑Score: kombiniere Fläche der Bounding‑Box mit quadratischer
    #     Abdeckung. Dadurch werden Punktwolken belohnt, die sowohl großflächig
    #     verteilt als auch gleichmäßig über die Bildquadranten verteilt sind.
    coverage_score = coverage_area * coverage
    coverage_score = max(0.0, min(coverage_score, 1.0))

    # 4) Logistische Normalisierung des Inlier‑Anteils. Anstatt den rohen
    #     Inlier‑Quotienten direkt zu verwenden, transformieren wir ihn mit
    #     einer einfachen saturierenden Funktion. So steigt der Wert rasch bei
    #     kleinen Inlier‑Quoten an, saturiert aber nahe 1.0.
    inlier_norm = 1.0 - float(np.exp(-max(inlier_ratio, 0.0) * 5.0)) if inlier_ratio is not None else 0.0

    # 5) Konditionszahl der Fundamentalmatrix als Degenerationsmaß. Eine sehr
    #     schlecht konditionierte F (z.B. bei planaren Szenen oder nahezu
    #     reiner Rotation) hat einen großen Quotienten zwischen den beiden
    #     kleinsten Singularwerten. Wir normieren diesen Wert, damit er
    #     maximal 1.0 beträgt und geben ihm als additive Strafe in die
    #     Fehlerschätzung ein.
    # Versuche die Konditionszahl der Fundamentalmatrix zu bestimmen. Falls dies
    # aufgrund numerischer Instabilität fehlschlägt, nehmen wir eine hohe
    # Penalty an, um das Paar konservativ zu behandeln.
    cond_ratio = None  # wird nach Möglichkeit gefüllt
    try:
        # Singuläre Werte in absteigender Reihenfolge (s[0] >= s[1] >= s[2]).
        _, svals, _ = np.linalg.svd(F)
        if len(svals) >= 3:
            cond_ratio = float(svals[1] / max(svals[2], 1e-12))
        else:
            cond_ratio = float('inf')
    except Exception:
        cond_ratio = float('inf')
    # Normiere den Degenerationswert. Ein cond_ratio >= 50 wird als komplett
    # degeneriert angesehen (Penalty = 1.0), darunter linear skaliert.
    if cond_ratio and np.isfinite(cond_ratio):
        deg_penalty = min(cond_ratio / 50.0, 1.0)
    else:
        deg_penalty = 1.0

    # 6) Kombiniertes Qualitätsmaß. Wir multiplizieren die normalisierten
    #     Größen und begrenzen das Ergebnis. Diese Kombination sorgt dafür,
    #     dass ein sehr schlechter Wert (z.B. extrem geringe Parallaxe)
    #     automatisch die Gesamtqualität senkt. Da die Werte jeweils im
    #     Bereich 0..1 liegen, bleibt das Produkt ebenfalls in diesem Bereich.
    combined_quality = float(inlier_norm * parallax_norm * coverage_score * track_len_norm)
    combined_quality = max(0.0, min(combined_quality, 1.0))

    # 7) Berechne die neue Qualitätssumme als gemitteltes additive Maß. Wir
    #     erhalten so eine zusätzliche, interpretierbare Kenngröße (0..1), die
    #     grob den Anteil guter Kriterien widerspiegelt. Die Gewichtung wurde
    #     bewusst belassen, um Abwärtskompatibilität herzustellen.
    quality_score = (
        0.4 * max(inlier_ratio, 0.0) if inlier_ratio is not None else 0.0
        + 0.3 * parallax_norm
        + 0.2 * coverage_score
        + 0.1 * track_len_norm
    )
    quality_score = max(0.0, min(quality_score, 1.0))

    # 8) Bestimmung der Homographie-Inlier und Fehlerschätzung.
    #     Zusätzlich zur Fundamentalmatrix wird eine Homographie geschätzt. Das
    #     Verhältnis der Homographie-Inlier zur Anzahl der Fundamentalmatrix-
    #     Inlier (hom_ratio) ist ein Indikator für planare Szenen bzw. reine
    #     Rotation. Dieser Wert fließt in die Fehlerschätzung ein: Je größer
    #     hom_ratio, desto höher predicted_error.
    hom_inliers = None
    hom_ratio = None
    try:
        H_h, h_mask = _ransac_H(pts1, pts2, iters=ransac_iters, thresh=ransac_thresh_px)
        if H_h is not None and h_mask is not None:
            hom_inliers = int(np.sum(h_mask))
            hom_ratio = float(hom_inliers) / float(max(inl_cnt, 1))
        else:
            hom_inliers = 0
            hom_ratio = None
    except Exception:
        hom_inliers = 0
        hom_ratio = None

    # 9) Fehlerschätzung. Der mediane Sampson-Fehler wird mit zwei
    #     Degenerationsstrafen (deg_penalty und hom_ratio) multipliziert und
    #     anschließend durch ein Produkt aus Inlier-Anteil, Parallaxe,
    #     Abdeckung und mittlerer Track-Länge geteilt. Eine kleine Konstante
    #     verhindert Division durch Null. Falls median_s nicht definiert ist,
    #     wird predicted_error unendlich.
    if np.isfinite(median_s) and (inlier_ratio is not None):
        denom = (
            max(inlier_ratio, 1e-6)
            * max(parallax_rms_norm, 1e-6)
            * max(coverage_score, 1e-6)
            * max(track_len_norm, 1e-6)
        )
        # Berücksichtige radiale Skalierung: bei Vorwärtsfahrt (>1) erhöht
        # der Faktor (1 + scale_norm) das Qualitätsprodukt und senkt den
        # predicted_error. scale_norm wird bei Berechnung oben gesetzt.
        try:
            scale_factor = 1.0 + float(scale_norm)
        except Exception:
            scale_factor = 1.0
        denom *= max(scale_factor, 1e-3)
        hr = 1.0 + float(hom_ratio) if (hom_ratio is not None and np.isfinite(hom_ratio)) else 1.0
        predicted_error = (median_s * (1.0 + deg_penalty) * hr) / denom
    else:
        predicted_error = float("inf")

    # 10) Degenerationsflag setzen: Zu wenig Inlier (<8), extrem geringe Parallaxe,
    #     schlecht konditionierte Fundamentalmatrix oder hoher Homographie-Anteil.
    degenerate_flag = False
    try:
        if inl_cnt < 8:
            degenerate_flag = True
        # Bei sehr geringer Parallaxe (<0.5 % der Diagonale) prüfen wir, ob eine
        # relevante radiale Skalierung vorliegt. Nur wenn scale_norm ebenfalls
        # sehr klein (<0.05), gilt das Paar als degeneriert.
        if parallax_norm < 0.005:
            try:
                if scale_norm is None or scale_norm < 0.05:
                    degenerate_flag = True
            except Exception:
                degenerate_flag = True
        if cond_ratio is None or not np.isfinite(cond_ratio) or cond_ratio > 50.0:
            degenerate_flag = True
        if hom_ratio is not None and hom_ratio > 0.8:
            degenerate_flag = True
    except Exception:
        degenerate_flag = True

    return PreSolveMetrics(
        frame_a=int(frame_a),
        frame_b=int(frame_b),
        inliers=inl_cnt,
        total=tot_cnt,
        median_sampson_px=median_s,
        mean_sampson_px=mean_s,
        parallax_median_px=parallax_med,
        parallax_p95_px=parallax_p95,
        coverage_quadrants=coverage,
        degenerate=degenerate_flag,
        F=F if return_F_and_mask else None,
        inlier_mask=inlier_mask if return_F_and_mask else None,
        inlier_ratio=inlier_ratio,
        track_count=track_count,
        avg_track_length=avg_len,
        median_track_length=med_len,
        coverage_area=coverage_area,
        quality_score=quality_score,
        predicted_error=predicted_error,
        hom_inliers=hom_inliers,
        hom_ratio=hom_ratio,
        scale_median=scale_median,
        scale_norm=scale_norm,
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
    require_continuous: bool = False,  # NEU
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

# ----------------------------------------------------------------------------
# Homography-Schätzung
# ----------------------------------------------------------------------------

def _compute_homography(p1: np.ndarray, p2: np.ndarray) -> Optional[np.ndarray]:
    """
    Berechnet eine Homographie H (3x3), die p1 → p2 abbildet, mittels DLT.

    Args:
        p1: (N x 2) Pixelkoordinaten der Ausgangspunkte.
        p2: (N x 2) Pixelkoordinaten der Zielpunkte.

    Returns:
        H als 3x3-Matrix, oder None bei numerischen Fehlern.
    """
    n = p1.shape[0]
    if n < 4:
        return None
    # Aufbau der DLT-Matrix
    A = []
    for i in range(n):
        x, y = float(p1[i, 0]), float(p1[i, 1])
        xp, yp = float(p2[i, 0]), float(p2[i, 1])
        A.append([0.0, 0.0, 0.0, -x, -y, -1.0, yp * x, yp * y, yp])
        A.append([x, y, 1.0, 0.0, 0.0, 0.0, -xp * x, -xp * y, -xp])
    A = np.asarray(A, dtype=np.float64)
    try:
        _, _, Vt = np.linalg.svd(A)
        h = Vt[-1, :]
        H = h.reshape(3, 3)
        # Normieren, sodass H[2,2] = 1 (falls möglich)
        if abs(H[2, 2]) > 1e-12:
            H = H / H[2, 2]
        return H
    except Exception:
        return None


def _transform_points_homography(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Transformiert 2D-Punkte mittels Homographie H."""
    pts_h = np.column_stack([pts, np.ones(len(pts))])
    tp = (H @ pts_h.T).T
    # homogenisieren
    w = tp[:, 2:3]
    w[w == 0.0] = 1e-12
    tp = tp[:, :2] / w
    return tp


def _ransac_H(
    p1: np.ndarray,
    p2: np.ndarray,
    *,
    iters: int = 500,
    thresh: float = 4.0,
    seed: int = 42,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    RANSAC-Schätzung für eine Homographie H.

    Args:
        p1: (N x 2) korrespondierende Punkte der ersten Ansicht (Pixel).
        p2: (N x 2) korrespondierende Punkte der zweiten Ansicht (Pixel).
        iters: Anzahl der RANSAC-Iterationen.
        thresh: Pixel-Schwelle für Inlier.
        seed: Zufallsstartwert.

    Returns:
        (H, inlier_mask) oder (None, None) bei Fehlschlag.
    """
    n = len(p1)
    if n < 4:
        return None, None
    rng = np.random.default_rng(seed)
    best_H: Optional[np.ndarray] = None
    best_mask: Optional[np.ndarray] = None
    best_count: int = 0
    for _ in range(max(1, iters)):
        try:
            idx = rng.choice(n, 4, replace=False)
        except Exception:
            continue
        H = _compute_homography(p1[idx], p2[idx])
        if H is None:
            continue
        # Vorwärtsprojektion p1 → p2
        proj = _transform_points_homography(H, p1)
        # euklidischer Abstand
        err = np.linalg.norm(proj - p2, axis=1)
        mask = err < thresh
        count = int(np.sum(mask))
        if count > best_count:
            best_count = count
            best_mask = mask
            best_H = H
    if best_H is None or best_mask is None or best_count < 4:
        return None, best_mask
    # Refit Homographie mit allen Inliern
    try:
        H_refit = _compute_homography(p1[best_mask], p2[best_mask])
        return H_refit, best_mask
    except Exception:
        return best_H, best_mask


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
