"""Feature Detection Wrapper.

Ruft bpy.ops.clip.detect_features mit berechneten Parametern auf.
"""
from __future__ import annotations

import bpy


def run_detect(context: bpy.types.Context, *, tr: float, md: float, ma: float):
    """Führt die Blender Feature Detection aus.

    Args:
        context: Blender Kontext (muss im CLIP_EDITOR sein)
        tr: threshold (float)
        md: min_distance (float oder int) -> wird gerundet
        ma: margin (float oder int) -> wird gerundet
    """
    if context.space_data is None or context.space_data.type != 'CLIP_EDITOR':
        print("[Kaiserlich Tracker][DETECT] Nicht im Clip Editor – Abbruch")
        return {'CANCELLED'}

    margin = int(round(ma))
    min_distance = int(round(md))
    threshold = float(tr)

    print(f"[Kaiserlich Tracker][DETECT] detect_features margin={margin} min_distance={min_distance} threshold={threshold}")
    try:
        res = bpy.ops.clip.detect_features(
            placement='FRAME',
            margin=margin,
            threshold=threshold,
            min_distance=min_distance,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[Kaiserlich Tracker][DETECT][ERROR] {e}")
        return {'CANCELLED'}
    print(f"[Kaiserlich Tracker][DETECT] Result {res}")
    return res
