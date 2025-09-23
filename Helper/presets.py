# Dünne Koordination der Helper (keine Heavy-Logik)


def load_preset(clip_id: str, roi_signature: dict) -> dict | None:
    """Return Startwerte für ähnliche Fälle (Resolution/Texture/Motion/Quadrant)."""
    raise NotImplementedError


def save_preset(clip_id: str, roi_signature: dict, params: dict, score: float) -> None:
    """Persistiere Best-Params; apply Aging & ε-greedy Exploration."""
    raise NotImplementedError