import bpy
import bpy
import math
from typing import Optional

def detect_features(
    context,
    *,
    placement='FRAME',
    margin: int = 100,
    threshold: float = 0.1,
    min_distance: int = 100
) -> Optional[int]:
    
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        return None
    # +10% Margin (immer größer, via ceil)
    eff_margin = int(math.ceil(margin * 1.1))

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
