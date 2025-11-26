import bpy
import math
from typing import Optional

def detect_features(
    context,
    *,
    placement: str = "FRAME",
    margin: int = 100,
    threshold: float = 0.1,
    min_distance: int = 100
) -> Optional[int]:
    """
    Führt bpy.ops.clip.detect_features aus und erhöht den übergebenen margin-Wert
    intern um +10% (aufgerundet), clamp auf [0, 300]. margin=0 bleibt 0.
    """
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        return None

    # +10% Regel: 0 bleibt 0, >0 wird aufgerundet und in [0,300] geclamped
    if margin <= 0:
        eff_margin = 0
    else:
        eff_margin = int(math.ceil(margin * 1.10))
        eff_margin = max(0, min(300, eff_margin))

    prev_count = len(clip.tracking.tracks)
    try:
        bpy.ops.clip.detect_features(
            placement=placement,
            margin=eff_margin,
            threshold=threshold,
            min_distance=min_distance
        )
    except Exception:
        return None

    new_count = len(clip.tracking.tracks)
    created = new_count - prev_count if new_count >= prev_count else None
    return created
