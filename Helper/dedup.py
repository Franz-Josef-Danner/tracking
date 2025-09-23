# KD-Tree/Grid-Distanzprüfungen


def build_index(existing_markers: list) -> object:
    """KD-Tree/Grid-Index vorbereiten."""
    raise NotImplementedError


def keep_if_far_enough(candidate, index, min_dist: float) -> bool:
    """True wenn Abstand ≥ min_dist; sonst False."""
    raise NotImplementedError


def feedback_min_distance(current_d: float, n: int, per_stage: int, pattern: int) -> float:
    """d_new = clamp(d * sqrt(n/per_stage), 2*pattern, 3.5*pattern)."""
    raise NotImplementedError