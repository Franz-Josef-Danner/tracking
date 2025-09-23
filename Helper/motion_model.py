# Loc→LocRot→LocRotScale→Affine→Perspective (Fit & Hysterese)

MODELS = [("LOC", 1), ("LOCROT", 2), ("LOCROTSCALE", 3), ("AFFINE", 4), ("PERSPECTIVE", 6)]


def fit_models(cluster, window: int = 30) -> dict:
    """RANSAC-Fits je Modell: return {name:{rms,out,inl,score}} mit Komplexitätsstrafe."""
    raise NotImplementedError


def select_model(prev: str, fits: dict, feats: dict, memory: dict) -> str:
    """Hysterese-Promotion (ΔS-Schwellen), Min-Inlier, Rollback-Checks."""
    raise NotImplementedError


def apply_model(cluster_id, model: str) -> None:
    """Setzt das Modell für Marker im Cluster."""
    raise NotImplementedError