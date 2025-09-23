# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

from typing import Any, Dict, Optional, Set, Tuple
import bpy

# ---------------------------------------------------------------------------
# Console logging
# ---------------------------------------------------------------------------
# In order to suppress debug output during marker detection, this module
# defines a no-op logger. All direct calls to ``print`` should be routed
# through ``_log`` to avoid writing to stdout.
def _log(*args, **kwargs):
    """No-op logger used to suppress console output."""
    return None

__all__ = ["perform_marker_detection", "run_detect_basic", "run_detect_once"]

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
            # Fallback fÃ¼r exotische Builds: wenigstens Threshold setzen
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
    """Setzt Marker via Operator-Args; gibt (pre_ptrs, new_count) zurÃ¼ck."""
    before = {t.as_pointer() for t in tracking.tracks}

    _detect_features(
        placement=placement,
        margin=int(margin_px),
        threshold=float(threshold),
        min_distance=int(min_distance_px),
    )

    # --- NEU: Zustand sicher â€žfluschenâ€œ ---
    scn = bpy.context.scene
    curf = int(scn.frame_current)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    try:
        # Frame kurz â€žanfassenâ€œ, damit marker-arrays intern frisch sind
        scn.frame_set(curf)
    except Exception:
        pass

    # --- Optional: kurze Warte-Schleife bis Keys am Frame sichtbar sind ---
    # (max. ~0.2 s; bricht frÃ¼her ab, sobald mind. 1 neuer Track einen Marker am curf hat)
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
    # Direkte, unveränderte Übergabe (vom Koordinator):
    margin: Optional[int] = None,
    min_distance: Optional[int] = None,
    # Legacy/Fallback (werden 1:1 übernommen – keine Skalierung):
    margin_base: Optional[int] = None,
    min_distance_base: Optional[int] = None,
    placement: Optional[str] = None,
    selection_policy: Optional[str] = None,   # ungenutzt
    # Legacy-Parameter (NO-OPs, für API-Kompatibilität):
    repeat_count: Optional[int] = None,
    match_search_size: Optional[bool] = None,
    # NEU: explizite Steuerung der Selektion
    select: Optional[bool] = None,
) -> Dict[str, Any]:
    """Setzt Marker am aktuellen (oder angegebenen) Frame.
    WICHTIG: Keine interne Umrechnung/Modifikation von margin/min_distance."""
    scn = context.scene

    # Reentrancy-Schutz
    if scn.get(_LOCK_KEY):
        return {"status": "FAILED", "reason": "locked"}

    scn[_LOCK_KEY] = True  # <-- WICHTIG: eigene Zeile!


    try:
        clip = _get_movieclip(context)
        print(f"[DETECT] Starte run_detect_basic auf Frame {scn.frame_current}")
        if not clip:
            print("[DETECT] Kein MovieClip gefunden!")
            return {"status": "FAILED", "reason": "no_movieclip"}

        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
                print(f"[DETECT] Setze Frame auf {start_frame}")
            except Exception as exc:
                print(f"[DETECT] Fehler beim Setzen des Start-Frames: {exc}")

        tracking = clip.tracking
        settings = tracking.settings

        # Defaults/Persistenz
        width = getattr(clip, "size", (0, 0))[0]
        height = getattr(clip, "size", (0, 0))[1]
        default_thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
        thr = float(threshold) if threshold is not None else default_thr

        # Baselines *ausschließlich* aus marker_helper_main (Scene-Keys), sonst konservative Defaults
        sb_margin = scn.get("margin_base", None)
        sb_min_dist = scn.get("min_distance_base", None)
        base_margin = int(sb_margin) if sb_margin is not None else max(16, int(0.025 * max(width, height)))
        base_min    = int(sb_min_dist) if sb_min_dist is not None else max(8,  int(0.025 * max(width, height)))

        # Direkte Übergabe vom Koordinator hat Vorrang; KEINE weitere Skalierung hier
        margin_px       = int(margin) if margin is not None else int(margin_base) if margin_base is not None else base_margin
        min_distance_px = int(min_distance) if min_distance is not None else int(min_distance_base) if min_distance_base is not None else base_min

        # Placement normalisieren (RNA-Enum erwartet 'FRAME' | 'INSIDE_GPENCIL' | 'OUTSIDE_GPENCIL')
        p = (placement or "FRAME").upper()
        print(f"[DETECT] Parameter: threshold={thr:.6f} margin_px={int(margin_px)} min_distance_px={int(min_distance_px)} placement={p}")
        # Marker vor Detect
        if clip:
            print(f"[DETECT] Marker vor Detect: {sum(len(t.markers) for t in clip.tracking.tracks)}")
            print(f"[DETECT] Marker pro Frame vor Detect: " + ", ".join([f"f{f}:{sum(1 for t in clip.tracking.tracks if t.markers.find_frame(f))}" for f in range(int(scn.frame_start), int(scn.frame_end)+1)]))

        pre_ptrs, new_count = perform_marker_detection(
            clip=clip,
            tracking=tracking,
            placement=p,
            threshold=thr,
            margin_px=margin_px,
            min_distance_px=min_distance_px,
        )
        # Marker nach Detect
        if clip:
            print(f"[DETECT] Marker nach Detect: {sum(len(t.markers) for t in clip.tracking.tracks)} (neu: {new_count})")
            print(f"[DETECT] Marker pro Frame nach Detect: " + ", ".join([f"f{f}:{sum(1 for t in clip.tracking.tracks if t.markers.find_frame(f))}" for f in range(int(scn.frame_start), int(scn.frame_end)+1)]))

        # --- Persistente Veröffentlichung aller effektiv genutzten Parameter ---
        try:
            s = settings
            scn["kc_detect_threshold"] = float(thr)
            scn["kc_detect_margin_px"] = int(margin_px)
            scn["kc_detect_min_distance_px"] = int(min_distance_px)
            scn["kc_detect_pattern_size"] = int(getattr(s, "default_pattern_size", 0))
            scn["kc_detect_search_size"] = int(getattr(s, "default_search_size", 0))
            # Einheitliche Key-Benennung für nachgelagerte Helfer (Multi, Distanze, ...)
            scn["kc_min_distance_effective"] = int(min_distance_px)
            _log(
                f"[Detect] publish: thr={scn['kc_detect_threshold']:.6f} "
                f"margin={scn['kc_detect_margin_px']} "
                f"min_dist={scn['kc_detect_min_distance_px']} "
                f"pattern={scn['kc_detect_pattern_size']} "
                f"search={scn['kc_detect_search_size']}"
            )
        except Exception:
            pass

        # Optionale Selektion neu erzeugter Tracks/Marker (für Downstream-Annahmen)
        want_select = True if select is None else bool(select)
        if want_select:
            try:
                cur_frame = int(scn.frame_current)
                created_tracks = [t for t in tracking.tracks if int(t.as_pointer()) not in pre_ptrs]
                for tr in created_tracks:
                    try:
                        tr.select = True
                    except Exception:
                        pass
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
                pass

        # Threshold persistieren (nur Threshold, keine margin/min_dist Persistenz)
        scn[DETECT_LAST_THRESHOLD_KEY] = float(thr)

        return {
            "status": "READY",
            "frame": int(scn.frame_current),
            "threshold": float(thr),
            "margin_px": int(margin_px),
            "min_distance_px": int(min_distance_px),
            "pattern_size": int(getattr(settings, "default_pattern_size", 0)),
            "search_size": int(getattr(settings, "default_search_size", 0)),
            "placement": p,
            # Debug/Transparenz:
            "repeat_count": int(repeat_count or 0),
            "triplet_mode": int(context.scene.get("_tracking_triplet_mode", 0) or 0),
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
    # kwargs (inkl. select) werden 1:1 durchgereicht
    res = run_detect_basic(context, **kwargs)
    if res.get("status") != "READY":
        return res
    return {
        "status": "READY",
        "frame": int(res.get("frame", bpy.context.scene.frame_current)),
        "threshold": float(res.get("threshold", 0.75)),
        "new_tracks": int(res.get("new_count_raw", 0)),
        # Telemetrie
        "margin_px": int(res.get("margin_px", 0)),
        "min_distance_px": int(res.get("min_distance_px", 0)),
        "repeat_count": int(res.get("repeat_count", 0)),
        "triplet_mode": int(res.get("triplet_mode", 0)),
    }
