# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

from typing import Any, Dict, Optional, Set, Tuple
import bpy
import math

__all__ = [
    "perform_marker_detection",
    "run_detect_basic",
    "run_detect_once",
]

# -----------------------------
# Scene Keys / State
# -----------------------------
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"
_LOCK_KEY = "tco_detect_lock"  # mit Coordinator konsistent

# -----------------------------
# Helpers
# -----------------------------
def _get_movieclip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    try:
        area = context.area
        if area and area.type == "CLIP_EDITOR":
            sp = area.spaces.active
            return getattr(sp, "clip", None)
    except Exception:
        pass
    # Fallback: aktive Szene
    try:
        return context.scene.clip
    except Exception:
        return None

def _ensure_clip_context(context: bpy.types.Context) -> Dict[str, Any]:
    """Findet einen CLIP_EDITOR und baut ein temp_override-Dict."""
    wm = bpy.context.window_manager
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {
                    "window": win,
                    "area": area,
                    "region": region,
                    "space_data": space,
                    "scene": bpy.context.scene,
                }
    return {}

def _detect_features(*, placement: str, margin: int, threshold: float, min_distance: int) -> None:
    """Robuster Aufruf von bpy.ops.clip.detect_features im CLIP-Kontext."""
    def _op(**kw):
        try:
            return bpy.ops.clip.detect_features(**kw)
        except TypeError:
            # Fallback für exotische Builds: wenigstens Threshold setzen
            return bpy.ops.clip.detect_features(threshold=float(max(threshold, 0.0001)))

    override = _ensure_clip_context(bpy.context)
    call_kwargs = dict(
        placement=str(placement),
        margin=int(margin),
        threshold=float(max(threshold, 0.0001)),
        min_distance=int(min_distance),
    )
    if override:
        with bpy.context.temp_override(**override):
            _op(**call_kwargs)
    else:
        _op(**call_kwargs)

# -----------------------------
# Kern: Marker-Detection
# -----------------------------
def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    *,
    placement: str,
    threshold: float,
    margin_px: int,
    min_distance_px: int,
) -> Tuple[Set[int], int]:
    """Setzt Marker via Operator-Args; gibt (pre_ptrs, new_count) zurück."""
    before = {t.as_pointer() for t in tracking.tracks}

    _detect_features(
        placement=placement,
        margin=int(margin_px),
        threshold=float(threshold),
        min_distance=int(min_distance_px),
    )

    # --- NEU: Zustand sicher „fluschen“ ---
    scn = bpy.context.scene
    curf = int(scn.frame_current)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    try:
        # Frame kurz „anfassen“, damit marker-arrays intern frisch sind
        scn.frame_set(curf)
    except Exception:
        pass

    # --- Optional: kurze Warte-Schleife bis Keys am Frame sichtbar sind ---
    # (max. ~0.2 s; bricht früher ab, sobald mind. 1 neuer Track einen Marker am curf hat)
    try:
        import time
        deadline = time.time() + 0.2
        while time.time() < deadline:
            created_tracks = [t for t in tracking.tracks if t.as_pointer() not in before]
            if any(t.markers.find_frame(curf, exact=True) for t in created_tracks):
                break
            # Einen kleinen Tick geben, dann erneut flushen
            time.sleep(0.01)
            bpy.context.view_layer.update()
            scn.frame_set(curf)
    except Exception:
        pass

    created = [t for t in tracking.tracks if t.as_pointer() not in before]
    return before, len(created)


# -----------------------------
# Public: Basic Detect
# -----------------------------
def run_detect_basic(
    context: bpy.types.Context,
    *,
    start_frame: Optional[int] = None,
    threshold: Optional[float] = None,
    margin_base: Optional[int] = None,
    min_distance_base: Optional[int] = None,
    placement: Optional[str] = None,
    selection_policy: Optional[str] = None,  # Placeholder für spätere Varianten
    # NEU: Wiederholungszähler & Policy für margin=search_size (Triplet/Multi)
    repeat_count: Optional[int] = None,
    match_search_size: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Setzt Marker am aktuellen (oder angegebenen) Frame und liefert Baseline-Infos.
    """
    scn = context.scene

    # Reentrancy-Schutz
    if scn.get(_LOCK_KEY):
        return {"status": "FAILED", "reason": "locked"}

    scn[_LOCK_KEY] = True  # <-- WICHTIG: eigene Zeile!

    try:
        clip = _get_movieclip(context)
        if not clip:
            return {"status": "FAILED", "reason": "no_movieclip"}

        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
            except Exception:
                pass

        tracking = clip.tracking
        tracks = tracking.tracks
        settings = tracking.settings

        # Defaults/Persistenz
        width = getattr(clip, "size", (0, 0))[0]
        height = getattr(clip, "size", (0, 0))[1]
        default_thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
        thr = float(threshold) if threshold is not None else default_thr

        # Baselines aus Szene lesen (Fallback: heuristische Defaults auf Clipgröße)
        sb_margin = scn.get("margin_base", None)
        sb_min_dist = scn.get("min_distance_base", None)
        base_margin = int(sb_margin) if sb_margin is not None else max(16, int(0.025 * max(width, height)))
        base_min    = int(sb_min_dist) if sb_min_dist is not None else max(8,  int(0.05  * max(width, height)))

        # Dynamische Skalierung anhand des aktuellen Thresholds (ohne Persistenz)
        safe   = max(thr * 1e8, 1e-8)  # numerisch stabil
        factor = math.log10(safe) / 8.0
        margin    = max(0, int(base_margin * factor))
        min_dist  = max(1, int(base_min    * factor))

        # NEU: Falls Triplet/Multi aktiv (repeat_count ≥ 6) ODER Szene-Triplet-Flag > 0
        # oder der Aufrufer explizit match_search_size=True setzt,
        # dann margin := aktuelle search_size, damit am Rand keine nicht-trackbaren
        # Features platziert werden.
        try:
            triplet_mode = int(context.scene.get("_tracking_triplet_mode", 0) or 0)
        except Exception:
            triplet_mode = 0
        try:
            rc = int(repeat_count or 0)
        except Exception:
            rc = 0
        # Dynamische Margin-Anpassung je nach repeat_count
        try:
            ps = int(getattr(settings, "default_pattern_size", 0))
        except Exception:
            ps = 0

        if match_search_size:
            # Nur wenn explizit angefordert → search_size verwenden
            try:
                ss = int(getattr(settings, "default_search_size", 0))
            except Exception:
                ss = 0
            if ss and ss > 0:
                margin = int(ss)

        # Staffelung auf Basis repeat_count
        if rc >= 26 and ps > 0:
            margin = ps * 12
        elif rc >= 21 and ps > 0:
            margin = ps * 10
        elif rc >= 16 and ps > 0:
            margin = ps * 8
        elif rc >= 11 and ps > 0:
            margin = ps * 6
        elif rc >= 6 and ps > 0:
            margin = ps * 4

        # Placement normalisieren (RNA-Enum erwartet 'FRAME' | 'INSIDE_GPENCIL' | 'OUTSIDE_GPENCIL')
        p = (placement or "FRAME").upper()

        # Debug-Ausgabe der berechneten Margin und Min-Distanz
        print(f"[Detect] frame={int(scn.frame_current)} "
              f"threshold={thr:.3f} margin_px={margin} min_distance_px={min_dist}")

        pre_ptrs, new_count = perform_marker_detection(
            clip=clip,
            tracking=tracking,
            placement=p,
            threshold=thr,
            margin_px=margin,
            min_distance_px=min_dist,
        )

        # Nach der Marker-Detection: neu erzeugte Spuren als „neu“ markieren
        # Ermitteln Sie alle Tracks, die im Vergleich zu pre_ptrs neu sind. Diese
        # werden als ausgewählt markiert, damit nachfolgende Distanzprüfungen
        # (run_distance_cleanup) sie als neue Marker erkennen können. Ohne diese
        # Selektion würden neu gesetzte Marker bei require_selected_new=True ignoriert.
        try:
            # Aktuellen Frame bestimmen
            cur_frame = int(scn.frame_current)
            created_tracks = [t for t in tracking.tracks if int(t.as_pointer()) not in pre_ptrs]
            for tr in created_tracks:
                # Track selektieren
                try:
                    tr.select = True
                except Exception:
                    pass
                # Marker am aktuellen Frame selektieren (wenn vorhanden)
                try:
                    m = None
                    try:
                        m = tr.markers.find_frame(cur_frame, exact=True)
                    except TypeError:
                        m = tr.markers.find_frame(cur_frame)
                    if m:
                        try:
                            m.select = True
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            # Bei jedem Fehler (z.B. ältere Blender-APIs) keine Selektion durchführen
            pass

        # Threshold persistieren (nur Threshold, keine margin/min_dist Persistenz)
        scn[DETECT_LAST_THRESHOLD_KEY] = float(thr)

        return {
            "status": "READY",
            "frame": int(scn.frame_current),
            "threshold": float(thr),
            "margin_px": int(margin),
            "min_distance_px": int(min_dist),
            "placement": p,
            # für Debug/Transparenz:
            "repeat_count": int(rc),
            "triplet_mode": int(triplet_mode),
            "pre_ptrs": pre_ptrs,
            "new_count_raw": int(new_count),
            "width": int(width),
            "height": int(height),
        }

    except Exception as ex:
        return {"status": "FAILED", "reason": f"{type(ex).__name__}: {ex}"}

    finally:
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass

# -----------------------------
# Thin Wrapper für Backward-Compat
# -----------------------------
def run_detect_once(context: bpy.types.Context, **kwargs) -> Dict[str, Any]:
    # kwargs kann nun repeat_count / match_search_size enthalten; wird 1:1 durchgereicht
    res = run_detect_basic(context, **kwargs)
    if res.get("status") != "READY":
        return res
    return {
        "status": "READY",
        "frame": int(res.get("frame", bpy.context.scene.frame_current)),
        "threshold": float(res.get("threshold", 0.75)),
        "new_tracks": int(res.get("new_count_raw", 0)),
        # Spiegeln für Telemetrie/Debugging
        "margin_px": int(res.get("margin_px", 0)),
        "repeat_count": int(res.get("repeat_count", 0)),
        "triplet_mode": int(res.get("triplet_mode", 0)),
    }
