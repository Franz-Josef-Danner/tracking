# 10f-Micro-Tracking-Checks (Corr/Residual/Jump)


def validate_markers(markers: list, frames: int = 10, corr_min: float = 0.60, jump_guard: bool = True) -> list:
    """Track kurz; filtere schlechte Kandidaten; return gefilterte Liste."""
    raise NotImplementedError


def trim_to_band(markers: list, target_hi: int) -> list:
    """Nach Qualität (corr, residual) & Diversität (nn_distance) ausdünnen."""
    raise NotImplementedError