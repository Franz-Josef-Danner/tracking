# Startwerte (pattern/search, alpha), Limit


def init_pattern_search(width: int, height: int, motion_score: float = 0.5) -> tuple[int, int, int]:
    """Return (pattern, alpha, search); search=round_even(alpha*pattern), Limits greifen."""
    raise NotImplementedError


def enforce_limits(pattern: int, alpha: int, width: int, height: int) -> tuple[int, int, int]:
    """Clamp pattern∈[9..41], alpha∈[2..4], search≤0.12*min_dim."""
    raise NotImplementedError