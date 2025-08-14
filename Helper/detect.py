# Helper/detect.py
import bpy
import math
import time
from contextlib import contextmanager

__all__ = [
    "perform_marker_detection",
    "run_detect_adaptive",
    "run_detect_once",
]

# ---------------------------------------------------------------------------
# UI-Context Guard
# ---------------------------------------------------------------------------

def _find_clip_area(win):
    if not win or not getattr(win, "screen", None):
        return None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            reg = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if reg:
                return area, reg
    return None, None

@contextmanager
def _ensure_clip_context(ctx, clip=None, *, allow_area_switch=False):
    """
    Sucht NUR vorhandene CLIP_EDITOR-Area. Kein Umschalten des Area-Typs.
    Liefert einen Override, der mit DEMSELBEN ctx (nicht bpy.context) aktiv ist.
    """
    win = getattr(ctx, "window", None)
    area, region = _find_clip_area(win)

    if area is None or region is None:
        # Kein gültiger Bereich verfügbar
        yield {}
        return

    space = area.spaces.active
    # Clip (falls angegeben) im Space setzen
    if clip is not None:
        try:
            space.clip = clip
        except Exception:
            pass
    # TRACKING-Mode (best effort)
    try:
        space.mode = 'TRACKING'
    except Exception:
        pass

    ovr = {'area': area, 'region': region, 'space_data': space}
    try:
        with ctx.temp_override(**ovr):
            yield ovr
    finally:
        pass

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _remove_tracks_by_name(tracking, names_to_remove):
    """Robustes Entfernen von Tracks per Datablock-API (ohne UI-Kontext)."""
    if not names_to_remove:
        return 0
    removed = 0
    for t in list(tracking.tracks):
        if t.name in names_to_remove:
            try:
                tracking.tracks.remove(t)
                removed += 1
            except Exception:
                pass
    return removed

def _collect_existing_positions(tracking, frame, w, h):
    pos = []
    for t in tracking.tracks:
        mk = t.markers.find_frame(frame)
        if mk:
            x = mk.co[0] * w
            y = mk.co[1] * h
            pos.append((x, y))
    return pos

def _dist2(p, q):
    dx = p[0] - q[0]
    dy = p[1] - q[1]
    return dx * dx + dy * dy

def _resolve_clip_from_context(ctx):
    space = getattr(ctx, "space_data", None)
    c = getattr(space, "clip", None) if space else None
    if c:
        return c
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None

def _clamp01(x: float) -> float:
    try:
        x = float(x)
    except Exception:
        return 0.0001
    if not math.isfinite(x):
        return 0.0001
    return min(1.0, max(0.0001, x))

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def perform_marker_detection(ctx, clip, tracking, threshold, margin_base, min_distance_base):
    """Führt detect_features im aktiven CLIP_EDITOR-Kontext aus. Keine Area-Umschaltung."""
    # Ableitungen
    factor = max(0.25, min(4.0, float(threshold) * 10.0))
    margin = max(1, int(margin_base * factor))
    min_dist = max(1, int(min_distance_base * factor))

    # High-Res Throttle: zu niedriger Threshold bei 4K+ führt zu Killer-Detektionen
    w, h = clip.size
    if w >= 4000 and threshold <= 0.01:
        min_dist = max(min_dist, int(w * 0.12))   # ~12% der Breite
        margin   = max(margin,   int(w * 0.04))   # ~4% der Breite

    with _ensure_clip_context(ctx, clip=clip, allow_area_switch=False) as ovr:
        sd = ovr.get('space_data')
        ar = ovr.get('area')
        rg = ovr.get('region')

        if not ar or not rg or not sd or getattr(sd, "clip", None) is None:
            return {"status": "failed", "reason": "no_valid_clip_context"}

        print(f"[Detect/DBG] area={getattr(ar,'type',None)} region={getattr(rg,'type',None)} "
              f"mode={getattr(sd,'mode',None)} has_clip={getattr(sd,'clip',None) is not None} "
              f"thr={threshold} margin={margin} min_dist={min_dist}")

        try:
            res = bpy.ops.clip.detect_features(
                threshold=float(threshold),
                min_distance=int(min_dist),
                margin=int(margin),
                placement='FRAME'
            )
        except Exception as ex:
            return {"status": "failed", "reason": f"detect_features exception: {ex}"}

    return {"status": "ok", "op_result": res, "threshold": float(threshold), "margin": margin, "min_distance": min_dist}

def run_detect_once(context, *, start_frame=None):
    clip = _resolve_clip_from_context(context)
    if clip is None:
        return {"status": "failed", "reason": "no_clip"}

    if start_frame is not None:
        with _ensure_clip_context(context, clip=clip, allow_area_switch=False) as ovr:
            if ovr:
                try:
                    context.scene.frame_current = int(start_frame)
                except Exception:
                    pass

    print("[Detect] Start-Threshold=", context.scene.get("last_detection_threshold", None))
    return run_detect_adaptive(context)

def run_detect_adaptive(context, *, detection_threshold=-1.0,
                        marker_adapt=-1, min_marker=-1, max_marker=-1,
                        margin_base=-1.0, min_distance_base=-1.0,
                        close_dist_rel=0.01, max_attempts=20, handoff_to_pipeline=False):
    scene = context.scene
    clip = _resolve_clip_from_context(context)
    if clip is None:
        return {"status": "failed", "reason": "no_clip"}

    tracking = clip.tracking
    ts = tracking.settings
    w, h = clip.size

    # Initial Threshold
    if detection_threshold is not None and detection_threshold >= 0:
        thr = float(detection_threshold)
    else:
        thr = float(scene.get("last_detection_threshold", ts.correlation_min if hasattr(ts, "correlation_min") else 0.9))
    thr = _clamp01(thr)
    scene["last_detection_threshold"] = thr

    # Ziele
    adapt = int(marker_adapt if marker_adapt >= 0 else int(scene.get("marker_adapt", scene.get("marker_basis", 20))))
    basis_for_bounds = max(1, int(adapt * 1.1))
    if min_marker >= 0 and max_marker >= 0:
        mn, mx = int(min_marker), int(max_marker)
    else:
        mn = int(scene.get("marker_min", int(basis_for_bounds * 0.9)))
        mx = int(scene.get("marker_max", int(basis_for_bounds * 1.1)))

    print(f"[Detect] Verwende min_marker={mn}, max_marker={mx} (Scene: min={scene.get('marker_min')}, max={scene.get('marker_max')})")

    # Baselines
    if margin_base is None or margin_base < 0:
        margin_base = max(1.0, w * 0.025)
    if min_distance_base is None or min_distance_base < 0:
        min_distance_base = max(1.0, w * 0.05)

    # Vorherige neue Tracks ggf. entfernen
    prev = list(scene.get("detect_prev_names", []))
    if prev:
        names_to_remove = set(prev)
        removed = _remove_tracks_by_name(tracking, names_to_remove)
        if removed:
            print(f"[Detect] Entfernt {removed} alte 'detect_prev_names'-Tracks")
        scene["detect_prev_names"] = []

    attempt = 0
    while attempt < int(max_attempts):
        current_frame = int(scene.frame_current)
        initial_names = [t.name for t in tracking.tracks]

        det_res = perform_marker_detection(context, clip, tracking, thr, margin_base, min_distance_base)
        if det_res.get("status") != "ok":
            return {"status": "failed", "reason": det_res.get("reason", "detect_failed")}

        # Warten bis Datenbank schreibt (max ~0.5s)
        waited = 0
        while waited < 50:
            if len(tracking.tracks) != len(initial_names):
                break
            time.sleep(0.01)
            waited += 1

        new_tracks = [t for t in tracking.tracks if t.name not in initial_names]

        existing_positions = _collect_existing_positions(tracking, current_frame, w, h)
        close_thr2 = (max(1.0, w * float(close_dist_rel))) ** 2
        close_names = []
        for t in new_tracks:
            mk = t.markers.find_frame(current_frame)
            if not mk:
                continue
            px = mk.co[0] * w
            py = mk.co[1] * h
            if any(_dist2((px, py), p) < close_thr2 for p in existing_positions):
                close_names.append(t.name)

        if close_names:
            removed = _remove_tracks_by_name(tracking, set(close_names))
            if removed:
                print(f"[Detect] Entfernte {removed} nahe/doppelte Tracks")

        cleaned_tracks = [t for t in tracking.tracks if (t.name not in initial_names) and (t.name not in close_names)]
        anzahl_neu = len(cleaned_tracks)

        if anzahl_neu < mn or anzahl_neu > mx:
            names_to_remove = [t.name for t in cleaned_tracks]
            if names_to_remove:
                _remove_tracks_by_name(tracking, set(names_to_remove))

            # Adaptive Threshold-Anpassung
            scale = max(0.1, (anzahl_neu + 0.1) / max(1.0, float(adapt)))
            thr = _clamp01(thr * scale)
            scene["last_detection_threshold"] = thr
            attempt += 1
            continue

        scene["detect_prev_names"] = [t.name for t in cleaned_tracks]
        if handoff_to_pipeline:
            scene["detect_status"] = "success"
            scene["pipeline_do_not_start"] = False
        else:
            scene["detect_status"] = "standalone_success"
            scene["pipeline_do_not_start"] = True

        return {
            "status": "success",
            "attempts": attempt + 1,
            "new_tracks": len(cleaned_tracks),
            "threshold": thr
        }

    scene["detect_status"] = "failed"
    return {"status": "failed", "attempts": attempt, "threshold": thr}
