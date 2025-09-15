# SPDX-License-Identifier: GPL-2.0-or-later

"""Multi-pass helper utilities."""

from __future__ import annotations
import bpy
import math
from typing import Iterable, Set, Dict, Any, Optional, Tuple, List

__all__ = ["run_multi_pass"]

# ------------------------------------------------------------
# Hilfen (lokal, keine Abhängigkeit vom Coordinator/Distanze)
# ------------------------------------------------------------
def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    scn = getattr(context, "scene", None)
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        space = getattr(context, "space_data", None)
        if space and getattr(space, "type", None) == "CLIP_EDITOR":
            clip = getattr(space, "clip", None)
    if not clip and scn:
        clip = getattr(scn, "clip", None)
    if not clip:
        try:
            clip = next(iter(bpy.data.movieclips))
        except Exception:
            clip = None
    return clip

def _marker_at_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    try:
        return track.markers.find_frame(int(frame), exact=True)
    except TypeError:
        return track.markers.find_frame(int(frame))

def _snapshot_selected_ptrs(clip: bpy.types.MovieClip, frame: int) -> Set[int]:
    out: Set[int] = set()
    for t in getattr(clip.tracking, "tracks", []):
        m = _marker_at_frame(t, frame)
        if not m:
            continue
        if getattr(t, "select", False) or getattr(m, "select", False):
            try:
                out.add(int(t.as_pointer()))
            except Exception:
                pass
    return out

def _snapshot_all_ptrs(clip: bpy.types.MovieClip) -> Set[int]:
    out: Set[int] = set()
    for t in getattr(clip.tracking, "tracks", []):
        try:
            out.add(int(t.as_pointer()))
        except Exception:
            pass
    return out

def _clear_selection_at_frame(clip: bpy.types.MovieClip, frame: int) -> None:
    for t in getattr(clip.tracking, "tracks", []):
        try:
            t.select = False
            m = _marker_at_frame(t, frame)
            if m:
                m.select = False
        except Exception:
            pass

def _select_ptrs_at_frame(clip: bpy.types.MovieClip, frame: int, ptrs: Iterable[int]) -> None:
    ptrs = set(int(p) for p in ptrs)
    for t in getattr(clip.tracking, "tracks", []):
        try:
            if int(t.as_pointer()) not in ptrs:
                continue
            m = _marker_at_frame(t, frame)
            if not m:
                continue
            t.select = True
            try:
                m.select = True
            except Exception:
                pass
        except Exception:
            pass

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


def _detect_once(*, threshold: float, margin: int, min_distance: int, placement: str = "FRAME") -> Dict:
    """Detect-Features im CLIP-Kontext mit expliziten Operator-Args (wie in detect.py)."""

    def _op(**kw):
        try:
            return bpy.ops.clip.detect_features(**kw)
        except TypeError:
            # Fallback: wenigstens Threshold setzen
            return bpy.ops.clip.detect_features(threshold=float(max(threshold, 0.0001)))

    res = _run_in_clip_context(
        _op,
        placement=str(placement).upper(),
        margin=int(margin),
        threshold=float(max(threshold, 0.0001)),
        min_distance=int(min_distance),
    )
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


def _run_multi_core(
    context: bpy.types.Context,
    *,
    detect_threshold: float,
    pre_ptrs: Set[int],
    repeat_count: Optional[int] = None,
    pattern_scales: Optional[List[float]] = None,
    adjust_search_with_pattern: bool = True,
    frame: Optional[int] = None,
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

    # --- Effektive min_distance **einmal** je Durchlauf bestimmen -----------
    scn = getattr(context, "scene", None)
    try:
        width, height = getattr(clip, "size", (0, 0))
    except Exception:
        width, height = 0, 0
    base_min_scene = scn.get("min_distance_base", None) if scn else None
    base_min = int(base_min_scene) if base_min_scene is not None else max(8, int(0.05 * max(width, height)))
    safe = max(float(detect_threshold) * 1e8, 1e-8)
    factor = math.log10(safe) / 8.0
    min_dist_effective = max(1, int(base_min * factor))
    if scn is not None:
        try:
            scn["kc_min_distance_effective"] = int(min_dist_effective)
            print(
                f"[Multi] f={int(scn.frame_current)} thr={float(detect_threshold):.6f} "
                f"→ min_distance_effective={int(min_dist_effective)} (base={int(base_min)})"
            )
        except Exception:
            pass
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

        # --- Margin/MinDist exakt wie in detect.py bestimmen (repeat-aware) ---
        rc = int(repeat_count or 0)
        ps = int(eff)  # effektive Pattern-Size dieses Sweeps
        try:
            ss = int(getattr(settings, "default_search_size", 0))
        except Exception:
            ss = 0

        # Margin-Staffel je repeat_count (ident zu detect.py)
        margin = 0
        if rc >= 26 and ps > 0:
            margin = ps * 24
        elif rc >= 21 and ps > 0:
            margin = ps * 20
        elif rc >= 16 and ps > 0:
            margin = ps * 16
        elif rc >= 11 and ps > 0:
            margin = ps * 12
        elif rc >= 6 and ps > 0:
            margin = ps * 8
        elif ss > 0:
            # Fallback analog "match_search_size"
            margin = ss

        # Min-Distance: den **vorab** berechneten Wert für alle Sweeps verwenden
        min_dist = int(min_dist_effective)

        # Debug-Logs: volle Transparenz je Sweep
        try:
            print(
                f"[Multi] f={int(context.scene.frame_current)} "
                f"scale={scale:.2f} eff_pattern={ps} search={ss} "
                f"repeat={rc} thr={float(detect_threshold):.3f} "
                f"→ margin={margin} min_dist={min_dist}"
            )
        except Exception:
            pass

        _detect_once(
            threshold=float(detect_threshold),
            margin=int(margin),
            min_distance=int(min_dist),
            placement="FRAME",
        )

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
        "created_low": int(created_per_scale.get(0.5, 0)),
        "created_high": int(created_per_scale.get(2.0, 0)),
        "created_per_scale": created_per_scale,
        "effective_pattern_sizes": eff_pattern_sizes,
        "selected": int(len(new_ptrs)),
        "new_ptrs": new_ptrs,
        "repeat_count": int(repeat_count or 0),
        "scales_used": scales,
        "min_distance_effective": int(min_dist_effective),
        "detect_threshold_used": float(detect_threshold),
    }


def run_multi_pass(context: bpy.types.Context, *, frame: Optional[int] = None, **kwargs) -> Dict[str, Any]:
    """
    Führt Multi aus, ohne den Detect-Cycle/Koordinator zu koppeln.
    - Snapshot der selektierten Marker @frame
    - Delta der neu entstandenen Tracks ermitteln
    - Selektion @frame = (Detect-Snapshot ∪ Multi-Neuzugänge)
    """
    clip = _resolve_clip(context)
    if not clip:
        return {"status": "NO_CLIP"}

    if frame is None:
        frame = int(getattr(getattr(context, "scene", None), "frame_current", 0))
    frame = int(frame)

    pre_selected_ptrs = _snapshot_selected_ptrs(clip, frame)
    pre_all_ptrs = _snapshot_all_ptrs(clip)

    core_res: Dict[str, Any] = {}
    if "_run_multi_core" in globals() and callable(globals()["_run_multi_core"]):
        core_res = globals()["_run_multi_core"](context, frame=frame, **kwargs) or {}

    post_all_ptrs = _snapshot_all_ptrs(clip)
    new_multi_ptrs = list(post_all_ptrs.difference(pre_all_ptrs))

    _clear_selection_at_frame(clip, frame)
    _select_ptrs_at_frame(clip, frame, pre_selected_ptrs.union(new_multi_ptrs))

    try:
        context.view_layer.update()
    except Exception:
        pass

    core_res.update({
        "status": core_res.get("status", "OK"),
        "frame": frame,
        "multi_new_ptrs": new_multi_ptrs,
        "restored_selected_ptrs": list(pre_selected_ptrs),
    })
    return core_res
