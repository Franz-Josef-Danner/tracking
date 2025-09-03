from __future__ import annotations
from typing import Dict, Optional, Set, List, Tuple
import bpy

__all__ = ["run_multi_pass"]

# Hinweis: Dieser Helper ist jetzt „repeat-aware“. Er kann anhand des
# Wiederholungszählers (count) unterschiedliche Pattern-Scans fahren.

def _run_in_clip_context(op_callable, **kwargs):
    wm = bpy.context.window_manager
    if wm:
        for window in wm.windows:
            screen = window.screen
            if not screen:
                continue
            for area in screen.areas:
                if area.type == "CLIP_EDITOR":
                    region = next((r for r in area.regions if r.type == "WINDOW"), None)
                    space = area.spaces.active if hasattr(area, "spaces") else None
                    if region and space:
                        override = {
                            "window": window,
                            "area": area,
                            "region": region,
                            "space_data": space,
                            "scene": bpy.context.scene,
                        }
                        with bpy.context.temp_override(**override):
                            return op_callable(**kwargs)
    return op_callable(**kwargs)

def _set_pattern_size(tracking: bpy.types.MovieTracking, new_size: int) -> int:
    s = tracking.settings
    clamped = max(3, min(101, int(new_size)))
    try:
        s.default_pattern_size = clamped
    except Exception:
        pass
    return int(getattr(s, "default_pattern_size", clamped))


def _detect_once(threshold: float) -> Dict:
    """Robust einen Detect-Features-Call innerhalb/außerhalb des CLIP-Kontexts ausführen."""

    def _op(**kw):
        try:
            return bpy.ops.clip.detect_features(**kw)
        except TypeError:
            return bpy.ops.clip.detect_features()

    res = _run_in_clip_context(_op, threshold=float(threshold))
    return {"op": "detect_features", "result": str(res)}


def _build_scales_for_repeat(repeat_count: Optional[int]) -> List[float]:
    """
    Mapping laut Anforderung:
      - <6  → keine Spezialbehandlung (leer; der Coordinator soll Multi dann ohnehin skippen)
      - 6   → [0.5, 2.0]
      - 7   → [0.5, 2.0, 3.0]
      - 8   → [0.5, 2.0, 3.0, 4.0]
      - 9+  → [0.5, 2.0, 3.0, 4.0, 5.0]
    """
    if not repeat_count or repeat_count < 6:
        return []
    base = [0.5, 2.0]
    if repeat_count >= 7:
        base.append(3.0)
    if repeat_count >= 8:
        base.append(4.0)
    if repeat_count >= 9:
        base.append(5.0)
    return base


def run_multi_pass(
    context: bpy.types.Context,
    *,
    detect_threshold: float,
    pre_ptrs: Set[int],
    # NEU: Wiederholungszähler (vom Coordinator aus tracking_state übergeben)
    repeat_count: Optional[int] = None,
    # Fallback: wenn repeat_count nicht gesetzt ist, kann man optional eigene
    # Skalen erzwingen. Wird ignoriert, sobald repeat_count >= 6 übergeben ist.
    pattern_scales: Optional[List[float]] = None,
    adjust_search_with_pattern: bool = True,
) -> Dict:
    """
    Führt zusätzliche Detect-Durchläufe mit identischem threshold aus,
    variiert Pattern(- und optional Search-)Size gemäß Wiederholungszähler
    (count). Sammelt NUR neue Marker relativ zu pre_ptrs und selektiert diese.
    Rückgabe enthält pro Scale die erzeugte Markeranzahl.
    """
    clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)
    if not clip:
        for c in bpy.data.movieclips:
            clip = c
            break
    if not clip:
        return {"status": "FAILED", "reason": "no_movieclip"}

    tracking = clip.tracking
    settings = tracking.settings
    pattern_o = int(getattr(settings, "default_pattern_size", 15))
    search_o  = int(getattr(settings, "default_search_size", 51))

    # Skalen bestimmen (repeat-aware). Wenn repeat_count >= 6, hat diese
    # Regel Priorität. Andernfalls optional pattern_scales verwenden, sonst
    # die ursprüngliche 2-Pass-Logik (0.5, 2.0).
    scales: List[float]
    rep_scales = _build_scales_for_repeat(repeat_count)
    if rep_scales:
        scales = rep_scales
    elif pattern_scales:
        scales = [float(s) for s in pattern_scales if s and float(s) > 0.0]
        if not scales:
            scales = [0.5, 2.0]
    else:
        scales = [0.5, 2.0]

    def _sweep(scale: float) -> Tuple[int, int]:
        """
        Setzt Pattern/Search Size gemäß scale, triggert Detect,
        liefert (created_count, effective_pattern_size).
        """
        before = {t.as_pointer() for t in tracking.tracks}
        before |= set(pre_ptrs)  # pre_ptrs sicherstellen
        eff = _set_pattern_size(tracking, max(3, int(round(pattern_o * float(scale)))))
        if adjust_search_with_pattern:
            try:
                settings.default_search_size = max(5, eff * 2)
            except Exception:
                pass
        _detect_once(threshold=float(detect_threshold))

        created = [t for t in tracking.tracks if t.as_pointer() not in before]
        return len(created), eff

    # Durchläufe gemäß Skalenliste
    created_per_scale: Dict[float, int] = {}
    eff_pattern_sizes: Dict[float, int] = {}
    for sc in scales:
        c, eff_size = _sweep(float(sc))
        created_per_scale[float(sc)] = int(c)
        eff_pattern_sizes[float(sc)] = int(eff_size)

    # restore sizes
    _set_pattern_size(tracking, pattern_o)
    try:
        settings.default_search_size = search_o
    except Exception:
        pass

    # Nur NEUE (Triplets) selektieren
    new_ptrs = {t.as_pointer() for t in tracking.tracks if t.as_pointer() not in pre_ptrs}
    for t in tracking.tracks:
        t.select = (t.as_pointer() in new_ptrs)

    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass

    return {
        "status": "READY",
        # für Backwards-Kompatibilität: aggregierte „low/high“-Werte, falls vorhanden
        "created_low": int(created_per_scale.get(0.5, 0)),
        "created_high": int(created_per_scale.get(2.0, 0)),
        # NEU: detaillierte Aufschlüsselung
        "created_per_scale": created_per_scale,
        "effective_pattern_sizes": eff_pattern_sizes,
        "selected": int(len(new_ptrs)),
        "new_ptrs": new_ptrs,
        "repeat_count": int(repeat_count or 0),
        "scales_used": scales,
    }
