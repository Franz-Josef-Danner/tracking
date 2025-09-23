# Loc→LocRot→LocRotScale→Affine→Perspective (Fit & Hysterese)
from __future__ import annotations
from typing import Dict, Any, Tuple

# Modellkomplexitäten κ laut Vorgabe
MODELS = [
    ("LOC", 1),
    ("LOCROT", 2),
    ("LOCROTSCALE", 3),
    ("AFFINE", 4),
    ("PERSPECTIVE", 6),
]

# interne Zustände (z. B. letztes Modell je Cluster, Scores)
_MEM: Dict[str, Dict[str, Any]] = {}


def _key(cluster_id: Any) -> str:
    return f"{cluster_id}"


def _complexity(name: str) -> int:
    for n, k in MODELS:
        if n == name:
            return k
    return 99


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _infer_feats(cluster: dict | None) -> Dict[str, float]:
    """Leite einfache Merkmale ab; falls keine Infos vorhanden, konservative Defaults.
    Verfügbare Felder (optional):
      - sigma_rot (deg), sigma_scale (rel), phi_shear, parallax, inliers
    """
    c = cluster or {}
    s = c.get("stats", {}) if isinstance(c, dict) else {}
    # Bevorzugt Werte aus stats, sonst aus Cluster; None → Default 0.0/12/1.0
    sigma_rot = s.get("sigma_rot") if isinstance(s, dict) else None
    if sigma_rot is None:
        sigma_rot = c.get("sigma_rot") if isinstance(c, dict) else None
    sigma_scale = s.get("sigma_scale") if isinstance(s, dict) else None
    if sigma_scale is None:
        sigma_scale = c.get("sigma_scale") if isinstance(c, dict) else None
    phi_shear = s.get("phi_shear") if isinstance(s, dict) else None
    if phi_shear is None:
        phi_shear = c.get("phi_shear") if isinstance(c, dict) else None
    parallax = s.get("parallax") if isinstance(s, dict) else None
    if parallax is None:
        parallax = c.get("parallax") if isinstance(c, dict) else None
    inliers = s.get("inliers") if isinstance(s, dict) else None
    if inliers is None:
        inliers = c.get("inliers") if isinstance(c, dict) else None
    rms_base = s.get("rms") if isinstance(s, dict) else None
    if rms_base is None:
        rms_base = c.get("rms") if isinstance(c, dict) else None
    outliers = s.get("outliers") if isinstance(s, dict) else None
    if outliers is None:
        outliers = c.get("outliers") if isinstance(c, dict) else None
    return {
        "sigma_rot": _safe_float(sigma_rot, 0.0),
        "sigma_scale": _safe_float(sigma_scale, 0.0),
        "phi_shear": _safe_float(phi_shear, 0.0),
        "parallax": _safe_float(parallax, 0.0),
        "inliers": _safe_float(inliers, 12.0),
        "rms_base": _safe_float(rms_base, 1.0),
        "outliers": _safe_float(outliers, 0.0),
    }


def _penalized_score(rms: float, name: str, lam: float = 0.12) -> float:
    return float(rms) + float(lam) * float(_complexity(name))


def fit_models(cluster, window: int = 30) -> dict:
    """RANSAC-Fits je Modell: return {name:{rms,out,inl,score}} mit Komplexitätsstrafe.
    Minimal: nutzt Heuristiken aus Cluster-Merkmalen statt echtem Fit.
    """
    feats = _infer_feats(cluster)
    base = max(0.25, feats["rms_base"])  # px

    # Heuristiken für RMS pro Modell, abhängig von Triggern
    rms_vals: Dict[str, float] = {
        "LOC": base,
        "LOCROT": base * (0.90 if feats["sigma_rot"] >= 0.5 else 1.02),
        "LOCROTSCALE": base * (0.85 if feats["sigma_scale"] >= 0.015 else 1.03),
        "AFFINE": base * (0.80 if feats["phi_shear"] >= 0.15 else 1.05),
        "PERSPECTIVE": base * (0.75 if feats["parallax"] >= 0.5 else 1.08),
    }

    out: Dict[str, Dict[str, float]] = {}
    inl = max(0, int(round(feats["inliers"])))
    outl = max(0, int(round(feats["outliers"])))
    for name, _k in MODELS:
        rms = float(rms_vals.get(name, base))
        out[name] = {
            "rms": rms,
            "out": float(outl),
            "inl": float(inl),
            "score": _penalized_score(rms, name),
        }
    return out


def select_model(prev: str | None, fits: dict, feats: dict | None, memory: dict | None = None) -> str:
    """Hysterese-Promotion (ΔS-Schwellen), Min-Inlier, Rollback-Checks.
    - S(M) = RMS + λ·κ
    - Promotionschwellen gemäß Vorgabe
    - Min-Inlier ≥ 8
    - Ohne valide Verbesserung bleibe bei prev
    """
    if not fits:
        return prev or "LOC"

    # Mindestinlier prüfen
    min_inl = 8
    if min((v.get("inl", 0.0) for v in fits.values())) < min_inl:
        return prev or "LOC"

    feats = feats or {}

    # Bestes Modell nach Score
    best_name, best_val = None, None
    for name, _k in MODELS:
        val = fits.get(name)
        if not isinstance(val, dict):
            continue
        if best_val is None or float(val.get("score", 1e9)) < float(best_val.get("score", 1e9)):
            best_name, best_val = name, val

    if best_name is None:
        return prev or "LOC"

    prev = prev or "LOC"
    if best_name == prev:
        return prev

    # ΔS zwischen prev und Kandidat
    s_prev = float(fits.get(prev, {}).get("score", 1e9))
    s_cand = float(fits.get(best_name, {}).get("score", 1e9))
    dS = s_prev - s_cand

    # Promotionsregeln
    sigma_rot = float(feats.get("sigma_rot", 0.0))
    sigma_scale = float(feats.get("sigma_scale", 0.0))
    phi_shear = float(feats.get("phi_shear", 0.0))
    parallax = float(feats.get("parallax", 0.0))
    outlier_prev = float(fits.get(prev, {}).get("out", 0.0))
    outlier_cand = float(fits.get(best_name, {}).get("out", 0.0))
    outlier_drop = outlier_prev - outlier_cand

    def allow_promotion(a: str, b: str) -> bool:
        # a→b
        if a == "LOC" and b == "LOCROT":
            return dS >= 0.30 or sigma_rot >= 0.5
        if a == "LOCROT" and b == "LOCROTSCALE":
            return dS >= 0.25 or (sigma_scale * 100.0) >= 1.5
        if a == "LOCROTSCALE" and b == "AFFINE":
            return dS >= 0.20 or (phi_shear >= 0.15 and outlier_drop >= 0.10 * max(1.0, outlier_prev))
        if a == "AFFINE" and b == "PERSPECTIVE":
            return dS >= 0.20 and (parallax >= 0.5 and outlier_drop >= 0.05 * max(1.0, outlier_prev))
        return False

    # Nur Promotions erlauben; Downgrade nur wenn deutlich besser
    if _complexity(best_name) > _complexity(prev):
        if allow_promotion(prev, best_name):
            return best_name
        return prev
    else:
        # Downgrade: erlaube, wenn klar besser
        return best_name if dS >= 0.15 else prev


def apply_model(cluster_id, model: str) -> None:
    """Setzt das Modell für Marker im Cluster (nur Zustand)."""
    _MEM.setdefault(_key(cluster_id), {})["model"] = str(model)


# ———————————— Schnittstellen-Wrapper ————————————

def cluster_fit_models(roi_id, window: int = 30) -> Dict[Any, Dict[str, Dict[str, float]]]:
    """Fit pro Cluster; return {cluster_id: fits}.
    Hinweis: nutzt Helper.roi.cluster_tracks (Platzhalter liefert leere Liste).
    """
    try:
        from .roi import cluster_tracks
    except Exception:
        cluster_tracks = None  # type: ignore
    fits_by_cluster: Dict[Any, Dict[str, Dict[str, float]]] = {}
    feats_by_cluster: Dict[Any, Dict[str, float]] = {}
    clusters = cluster_tracks(roi_id, window=window) if callable(cluster_tracks) else []
    for c in clusters or []:
        cid = c.get("id") if isinstance(c, dict) else None
        if cid is None:
            continue
        fits = fit_models(c, window=window)
        fits_by_cluster[cid] = fits
        feats_by_cluster[cid] = _infer_feats(c)
    return {"fits": fits_by_cluster, "feats": feats_by_cluster}


def select_apply_motion_models(roi_id, fits: Dict[Any, Dict[str, Dict[str, float]]], feats: Dict[Any, Dict[str, float]] | None = None) -> Dict[Any, str]:
    """Wähle Modell je Cluster mit Hysterese und setze es; return {cluster_id: model}."""
    decisions: Dict[Any, str] = {}
    feats = feats or {}
    for cid, f in (fits or {}).items():
        prev = _MEM.get(_key(cid), {}).get("model", "LOC")
        chosen = select_model(prev, f, feats.get(cid, {}), _MEM)
        apply_model(cid, chosen)
        decisions[cid] = chosen
    return decisions