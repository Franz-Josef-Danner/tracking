import bpy
from typing import Dict
from .properties import (
    get_repeat_count,
    get_repeat_radius,
    merge_repeat_series,
)


def _build_repeat_series(center_frame: int, base_count: int, radius: int) -> Dict[int, int]:
    """
    Erzeugt eine Frame->Count Serie mit 5-Frame-Decay:
      - Count(center) = base_count
      - Für Abstand d>=1: count = max(base_count - floor(d/5), 0)
    Beispiel: base=7 ⇒ d=0:7, 1..4:7, 5..9:6, 10..14:5, ...
    """
    series: Dict[int, int] = {}
    if base_count <= 0 or radius <= 0:
        series[center_frame] = max(base_count, 0)
        return series
    f0 = int(center_frame)
    # Szenegrenzen für Clamping (sicher gegen fehlenden Context)
    try:
        scn = bpy.context.scene
        fmin, fmax = int(scn.frame_start), int(scn.frame_end)
    except Exception:
        fmin, fmax = -10**9, 10**9
    for d in range(0, int(radius) + 1):
        dec = d // 5  # 5-Frame-Raster
        val = max(int(base_count) - int(dec), 0)
        if val <= 0:
            continue
        left = max(fmin, min(f0 - d, fmax))
        right = max(fmin, min(f0 + d, fmax))
        series[left] = max(series.get(left, 0), val)
        series[right] = max(series.get(right, 0), val)
    return series

def record_jump_repeat_and_update_overlay(context: bpy.types.Context, target_frame: int) -> None:
    """
    Kernroutine:
      1) Basis-Count am Ziel-Frame inkrementieren
      2) Serie mit 5-Frame-Decay bauen (Radius aus Scene-Property)
      3) Atomar in Scene-Map mergen (max-Merge) und Overlay-Redraw triggern
    """
    scene = context.scene
    target_frame = int(target_frame)
    base = get_repeat_count(scene, target_frame) + 1
    radius = get_repeat_radius(scene)
    series = _build_repeat_series(target_frame, base, radius)
    merge_repeat_series(scene, series)


def run_jump_to_frame(context: bpy.types.Context, frame: int) -> None:
    """Beispiel-Jump-Wrapper: Setzt Frame und protokolliert Repeat-Serien."""
    scene = context.scene
    scene.frame_set(int(frame))
    # Repeat-Serie erfassen und Overlay updaten
    record_jump_repeat_and_update_overlay(context, int(frame))

