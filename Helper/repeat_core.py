from __future__ import annotations
from typing import Dict
import bpy

# Zentrale Defaults
FADE_STEP_DEFAULT = 5


def get_fade_step(scene: bpy.types.Scene) -> int:
    try:
        val = int(getattr(scene, "kc_repeat_fade_step", FADE_STEP_DEFAULT))
        return max(1, val)
    except Exception:
        return FADE_STEP_DEFAULT


def get_series(scene: bpy.types.Scene) -> list[float]:
    fs = int(scene.frame_start)
    fe = int(scene.frame_end)
    n = max(0, fe - fs + 1)
    series = scene.get("_kc_repeat_series")
    if not isinstance(series, list) or len(series) != n:
        return [0.0] * n
    return series


def get_value(scene: bpy.types.Scene, frame: int) -> int:
    fs = int(scene.frame_start)
    ser = get_series(scene)
    idx = int(frame) - fs
    return int(ser[idx]) if 0 <= idx < len(ser) else 0


def expand_rings(center_f: int, k: int, fs: int, fe: int, step: int) -> Dict[int, int]:
    """
    Exakte 5er-Ringlogik:
      Ring 0 : [f-step .. f+step] → k
      Ring m≥1:
        L: [f-step*(m+1) .. f-(step*m+1)] → k-m
        R: [f+(step*m+1) .. f+step*(m+1)] → k-m
    Clamping auf [fs..fe], pro Frame MAX-Merge.
    """
    out: Dict[int, int] = {}
    if k <= 0:
        return out
    # Ring 0
    s0 = max(fs, center_f - step)
    e0 = min(fe, center_f + step)
    for i in range(s0, e0 + 1):
        if k > out.get(i, 0):
            out[i] = k
    # Ringe 1..k-1
    for m in range(1, k):
        val = k - m
        L1 = max(fs, center_f - step * (m + 1))
        L2 = max(fs, center_f - (step * m + 1))
        if L1 <= L2:
            for i in range(L1, L2 + 1):
                if val > out.get(i, 0):
                    out[i] = val
        R1 = min(fe, center_f + (step * m + 1))
        R2 = min(fe, center_f + step * (m + 1))
        if R1 <= R2:
            for i in range(R1, R2 + 1):
                if val > out.get(i, 0):
                    out[i] = val
    return out

