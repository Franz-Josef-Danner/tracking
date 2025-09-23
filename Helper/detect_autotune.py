# Detect-Parameter-Autotune (threshold, min_distance, etc.)


def propose_detect_profile(roi_id, texture: float, motion: float) -> dict:
    """Return {threshold, min_distance_base, nms_window, max_features, levels, edge_suppr}."""
    raise NotImplementedError


def adjust_detect_profile(kpis: dict, profile: dict) -> dict:
    """If-Then-Regeln: Fehlmatches, Coverage, Cluster → Profil feinjustieren."""
    raise NotImplementedError