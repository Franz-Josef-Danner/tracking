# SPDX-License-Identifier: GPL-2.0-or-later

"""Multi-pass helper utilities — STRICT detect-param reuse."""

from __future__ import annotations
import bpy
from typing import Iterable, Set, Dict, Any, Optional, Tuple, List

__all__ = ["run_multi_pass"]

# ---------------------------------------------------------------------------
# Lightweight logging (no side-effects). Always safe-guarded.
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    try:
        print(msg)
    except Exception:
        # Never fail due to logging
        pass

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
    (count).
    Log-Punkte:
      - Clip/Frame/Repeat/Canvasgröße
      - Quelle und Wert von min_distance_effective
      - Effektive Detect-Parameter (thr/margin/min_dist/pattern/search)
      - Per-Scale-Ergebnis (created, eff_pattern_size)
      - Auswahl-Delta (new_ptrs Count)
      - Summary (created_per_scale, selected)
      (Keine funktionalen Änderungen.)
    Sammelt NUR neue Marker relativ zu pre_ptrs und selektiert diese.
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

    scn = getattr(context, "scene", None)
    try:
        width, height = getattr(clip, "size", (0, 0))
    except Exception:
        width, height = 0, 0

    try:
        _log(
            f"[Multi.Core] ENTER clip={getattr(clip,'name','<unnamed>')} "
            f"size={int(width)}x{int(height)} repeat={int(repeat_count or 0)} "
            f"detect_threshold_in={float(detect_threshold):.6f} "
            f"frame={getattr(getattr(context,'scene',None),'frame_current',None)}"
        )
    except Exception:
        pass
    md_detect = None
    if scn is not None:
        md_detect = scn.get("kc_min_distance_effective", None)
        if md_detect is None:
            md_detect = scn.get("tco_detect_min_distance", None)
    if isinstance(md_detect, (int, float)) and float(md_detect) > 0.0:
        min_dist_effective = int(round(float(md_detect)))
        md_src = "detect"
    else:
        base_min_scene = scn.get("min_distance_base", None) if scn else None
        min_dist_effective = int(base_min_scene) if base_min_scene is not None else max(8, int(0.05 * max(width, height)))
        md_src = "fallback"
    try:
        frame_val = int(getattr(getattr(context, "scene", None), "frame_current", 0))
        # vorhandene Info beibehalten, aber um Prefix vereinheitlicht
        _log(
            f"[Multi.Core] f={frame_val} thr={float(detect_threshold):.6f} "
            f"→ min_distance_effective={int(min_dist_effective)} src={md_src}"
        )
    except Exception:
        pass

    # --- Detect-Parameter 1:1 übernehmen (kein Recompute, kein Scaling) ---
    thr = float(detect_threshold)
    margin = 0
    min_dist = 0
    if scn is not None:
        try:
            thr = float(scn.get("kc_detect_threshold", scn.get("last_detection_threshold", thr)))
        except Exception:
            thr = float(detect_threshold)
        try:
            margin = int(scn.get("kc_detect_margin_px", margin))
        except Exception:
            margin = int(margin)
        try:
            min_dist = int(scn.get("kc_detect_min_distance_px", scn.get("kc_min_distance_effective", min_dist)))
        except Exception:
            min_dist = int(min_dist)
    if min_dist <= 0:
        try:
            width, height = getattr(clip, "size", (0, 0))
        except Exception:
            width, height = 0, 0
        longest = max(int(width or 0), int(height or 0))
        min_dist = max(8, int(0.025 * longest)) if longest > 0 else 8

    ps = 0
    ss = 0
    try:
        if scn is not None:
            ps = int(scn.get("kc_detect_pattern_size", 0) or 0)
            ss = int(scn.get("kc_detect_search_size", 0) or 0)
        if ps > 0:
            _set_pattern_size(tracking, ps)
        if ss > 0:
            settings.default_search_size = ss
    except Exception:
        ps = 0
        ss = 0

    try:
        margin = int(scn.get("tco_detect_margin", 0) or scn.get("margin_base", 0))
    except Exception:
        margin = 0
    if margin <= 0 and ss > 0:
        margin = int(ss)

    min_dist = int(min_dist_effective)

    pattern_o = int(getattr(settings, "default_pattern_size", 15))
    search_o  = int(getattr(settings, "default_search_size", 51))

    # KEINE Skalenvarianten mehr: exakt die Detect-Werte (Scale = 1.0)
    scales: List[float] = [1.0]

    try:
        _log(
            f"[Multi.Core] Params reuse (pre-sweep): "
            f"thr={thr:.6f} margin={int(margin)} min_dist={int(min_dist)} "
            f"pattern_o={int(pattern_o)} search_o={int(search_o)} "
            f"scales={scales}"
        )
    except Exception:
        pass

    def _sweep(scale: float) -> Tuple[int, int]:
        """
        Setzt Pattern/Search Size gemäß scale, triggert Detect,
        liefert (created_count, effective_pattern_size).
        """
        before = {t.as_pointer() for t in tracking.tracks}
        before |= set(pre_ptrs)  # pre_ptrs sicherstellen
        eff = _set_pattern_size(tracking, max(3, int(round(pattern_o * float(scale)))))
        # Search unverändert lassen – wir spiegeln Detect-Params.
        try:
            settings.default_search_size = search_o
        except Exception:
            pass

        # Margin/MinDist/Threshold 1:1 aus Detect übernehmen
        ps = int(eff)
        try:
            ss = int(getattr(settings, "default_search_size", 0))
        except Exception:
            ss = 0
        _margin = int(margin)
        _min_dist = int(min_dist)
        _thr = float(thr)

        # Debug (bestehende Ausgabe beibehalten, Prefix vereinheitlicht)
        try:
            _log(
                f"[Multi.Core] reuse DETECT: f={int(context.scene.frame_current)} "
                f"ps={ps} ss={ss} thr={_thr:.6f} margin={_margin} min_dist={_min_dist}"
            )
        except Exception:
            pass

        try:
            _log(f"[Multi.Sweep] BEGIN scale={scale} eff_ps={ps} ss={ss}")
        except Exception:
            pass

        _detect_once(
            threshold=_thr,
            margin=_margin,
            min_distance=_min_dist,
            placement="FRAME",
        )

        created = [t for t in tracking.tracks if t.as_pointer() not in before]
        try:
            _log(f"[Multi.Sweep] END   scale={scale} created={len(created)} eff_ps={eff}")
        except Exception:
            pass
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

    try:
        _log(
            f"[Multi.Core] Sweep summary: created_per_scale={created_per_scale} "
            f"eff_pattern_sizes={eff_pattern_sizes}"
        )
    except Exception:
        pass

    # Nur NEUE (Triplets) selektieren
    new_ptrs = {t.as_pointer() for t in tracking.tracks if t.as_pointer() not in pre_ptrs}
    for t in tracking.tracks:
        t.select = (t.as_pointer() in new_ptrs)

    # Telemetrie: Publiziere erneut den MinDist-Wert (keine Änderung, reines Echo)
    if scn is not None:
        try:
            scn["kc_min_distance_effective"] = int(min_dist)
        except Exception:
            pass

    try:
        _log(
            f"[Multi.Core] Selected new_ptrs={len(new_ptrs)} "
            f"repeat_count={int(repeat_count or 0)}"
        )
    except Exception:
        pass

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
        "min_distance_effective": int(min_dist),
        "detect_threshold_used": float(thr),
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

    try:
        w, h = getattr(clip, "size", (0, 0))
    except Exception:
        w, h = 0, 0
    try:
        _log(
            f"[Multi] START frame={frame} clip={getattr(clip,'name','<unnamed>')} "
            f"size={int(w)}x{int(h)} kwargs_keys={list(kwargs.keys())}"
        )
    except Exception:
        pass

    pre_selected_ptrs = _snapshot_selected_ptrs(clip, frame)
    pre_all_ptrs = _snapshot_all_ptrs(clip)
    try:
        _log(
            f"[Multi] Snapshot pre: selected={len(pre_selected_ptrs)} "
            f"all={len(pre_all_ptrs)}"
        )
    except Exception:
        pass

    core_res: Dict[str, Any] = {}
    if "_run_multi_core" in globals() and callable(globals()["_run_multi_core"]):
        core_res = globals()["_run_multi_core"](context, frame=frame, **kwargs) or {}
    try:
        _log(
            f"[Multi] Core status={core_res.get('status','?')} "
            f"created_low={core_res.get('created_low')} "
            f"created_high={core_res.get('created_high')} "
            f"selected={core_res.get('selected')}"
        )
    except Exception:
        pass

    post_all_ptrs = _snapshot_all_ptrs(clip)
    new_multi_ptrs = list(post_all_ptrs.difference(pre_all_ptrs))
    try:
        _log(
            f"[Multi] Snapshot post: all={len(post_all_ptrs)} "
            f"delta_new={len(new_multi_ptrs)}"
        )
    except Exception:
        pass

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

    try:
        _log(
            f"[Multi] END frame={frame} status={core_res.get('status')} "
            f"delta_new={len(new_multi_ptrs)} restored_selected={len(pre_selected_ptrs)}"
        )
    except Exception:
        pass
    return core_res
