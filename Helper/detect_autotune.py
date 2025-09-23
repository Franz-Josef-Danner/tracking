# Detect-Parameter-Autotune (threshold, min_distance, etc.)
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict


# interne Grenzen laut Spezifikation
THRESH_MIN = 1e-5
THRESH_MAX = 1e-2
LEVELS_MIN, LEVELS_MAX = 1, 3


@dataclass
class DetectProfile:
    # Schwellenwert im log-Bereich (1e-5 .. 1e-2)
    threshold: float
    # Multi-Scale Ebenen 1..3
    levels: int
    # Kantenunterdrückung
    edge_suppr: bool
    # Kapazität je ROI
    max_features: int
    # Anstelle absoluter Pixelwerte geben wir Faktoren relativ zum pattern aus.
    # So kann die Pipeline (z. B. Staged Seeding) die aktuellen pattern-Werte einsetzen.
    min_distance_factor: float = 2.5
    nms_window_factor: float = 1.0

    def as_dict(self) -> Dict:
        return {
            "threshold": float(self.threshold),
            "levels": int(self.levels),
            "edge_suppr": bool(self.edge_suppr),
            "max_features": int(self.max_features),
            "min_distance_factor": float(self.min_distance_factor),
            "nms_window_factor": float(self.nms_window_factor),
        }


def _interp_log_threshold(texture: float) -> float:
    """texture∈[0,1] → threshold in [1e-5, 1e-2];
    Low-Texture ⇒ niedriger threshold (sensitiver)."""
    t = max(0.0, min(1.0, texture))
    # log10(threshold) in [-5 .. -2]
    logv = -5.0 + 3.0 * t
    return max(THRESH_MIN, min(THRESH_MAX, 10.0 ** logv))


def propose_detect_profile(roi_id, texture: float, motion: float) -> dict:
    """Return {threshold, min_distance_factor, nms_window_factor, max_features, levels, edge_suppr}.

    Regeln:
    - Low-Texture/Blur → threshold↓, levels↑, max_features↑
    - High-Motion → ggf. levels 2, robustere Kapazität
    - min_distance/nms als Faktoren relativ zum pattern (2.5x bzw. 1.0x)
    """
    thr = _interp_log_threshold(texture)

    # Levels: 3 bei sehr niedriger Textur, 2 bei mittlerer, sonst 1
    if texture < 0.30:
        levels = 3
    elif texture < 0.60:
        levels = 2
    else:
        levels = 1

    # leichte Anhebung der Ebenen bei sehr hoher Bewegung
    if motion >= 0.75:
        levels = min(LEVELS_MAX, max(levels, 2))

    # Kapazität: mehr Features bei niedriger Textur
    if texture < 0.30:
        max_feats = 1200
    elif texture < 0.60:
        max_feats = 800
    else:
        max_feats = 500

    # Edge suppression zunächst aus
    edge = False

    prof = DetectProfile(
        threshold=thr,
        levels=max(LEVELS_MIN, min(LEVELS_MAX, levels)),
        edge_suppr=edge,
        max_features=max_feats,
    )
    return prof.as_dict()


def adjust_detect_profile(kpis: dict, profile: dict) -> dict:
    """If-Then-Regeln: Fehlmatches, Coverage, Cluster → Profil feinjustieren.

    Erwartete KPI-Felder (optional):
      - mismatch_rate [0..1]
      - coverage [0..1], target_coverage [0..1]
      - clusters_dense (bool) oder mean_nn (px)
      - texture [0..1] (falls bekannt)
      - runtime_pressure (bool) → Kapazität senken
    """
    prof = dict(profile)  # copy

    def _get(name, default=None):
        return kpis.get(name, default)

    # 1) Viele Fehlmatches → edge_suppression an, threshold rauf, min_distance rauf
    mismatch = _get("mismatch_rate", 0.0) or 0.0
    if mismatch > 0.15:
        prof["edge_suppr"] = True
        prof["threshold"] = min(THRESH_MAX, (prof.get("threshold", THRESH_MIN) or THRESH_MIN) * 1.5)
        prof["min_distance_factor"] = float(prof.get("min_distance_factor", 2.5)) * 1.10

    # 2) Coverage zu niedrig und Textur gering → threshold runter, levels rauf, Kapazität rauf
    coverage = _get("coverage", None)
    target_cov = _get("target_coverage", 0.80)
    texture = _get("texture", 0.5)
    if coverage is not None and coverage < 0.8 * target_cov and texture < 0.45:
        prof["threshold"] = max(THRESH_MIN, (prof.get("threshold", THRESH_MAX) or THRESH_MAX) * 0.5)
        prof["levels"] = int(max(LEVELS_MIN, min(LEVELS_MAX, int(prof.get("levels", 1)) + 1)))
        prof["max_features"] = int((prof.get("max_features", 500) or 500) * 1.25)

    # 3) Clusterbildung/zu dichtes Sampling → min_distance rauf
    dense = bool(_get("clusters_dense", False))
    mean_nn = _get("mean_nn", None)
    if dense or (mean_nn is not None and mean_nn < 2.0 * (prof.get("min_distance_factor", 2.5) * 10.0)):
        prof["min_distance_factor"] = float(prof.get("min_distance_factor", 2.5)) * 1.15

    # 4) Runtime-Druck → Kapazität etwas drosseln, levels ggf. runter
    if bool(_get("runtime_pressure", False)):
        prof["max_features"] = max(200, int((prof.get("max_features", 500) or 500) * 0.85))
        if mismatch < 0.08:  # nur wenn stabil
            prof["levels"] = max(LEVELS_MIN, int(prof.get("levels", 1)) - 1)

    # Werte clampen
    prof["threshold"] = float(max(THRESH_MIN, min(THRESH_MAX, prof.get("threshold", THRESH_MIN))))
    prof["levels"] = int(max(LEVELS_MIN, min(LEVELS_MAX, int(prof.get("levels", 1)))))
    prof["max_features"] = int(max(100, min(5000, int(prof.get("max_features", 500)))))

    # Faktoren sinnvoll begrenzen
    prof["min_distance_factor"] = float(max(2.0, min(4.0, prof.get("min_distance_factor", 2.5))))
    prof["nms_window_factor"] = float(max(0.5, min(2.0, prof.get("nms_window_factor", 1.0))))

    return prof


# ———————————— API-Wrapper gemäß Pflichtenheft ————————————

def autotune_detect(roi_id, roi_info: dict | None = None, kpis: dict | None = None) -> dict:
    """Kompakte Schnittstelle: liefert ein abgestimmtes Detect-Profil für einen ROI.

    roi_info kann Felder enthalten: {texture: [0..1], motion: [0..1]}
    kpis können Laufzeit-/Qualitätsindikatoren liefern (siehe adjust_detect_profile).
    """
    roi_info = roi_info or {}
    texture = float(roi_info.get("texture", 0.5) or 0.5)
    motion = float(roi_info.get("motion", 0.5) or 0.5)
    base = propose_detect_profile(roi_id=roi_id, texture=texture, motion=motion)
    tuned = adjust_detect_profile(kpis or {"texture": texture}, base)
    return tuned