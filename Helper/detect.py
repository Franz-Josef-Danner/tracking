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

# --------------------------- Context helpers -----------------------------

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
    Use an existing CLIP_EDITOR area & its WINDOW region. No area type switching.
    Returns an override dict usable with ctx.temp_override(**ovr).
    """
    win = getattr(ctx, "window", None)
    area, region = _find_clip_area(win)
    if area is None or region is None:
        yield {}
        return
    space = area.spaces.active
    try:
        if clip is not None:
            space.clip = clip
        space.mode = 'TRACKING'
    except Exception:
        pass
    ovr = {"area": area, "region": region, "space_data": space}
    try:
        with ctx.temp_override(**ovr):
            yield ovr
    finally:
        pass

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

# ------------------------------- Detect ----------------------------------

def perform_marker_detection(ctx, clip, tracking, threshold, margin_base, min_distance_base):
    """
    Run bpy.ops.clip.detect_features in the SAME override from ctx.
    Returns a dict with status/op_result.
    """
    # scale margins from threshold
    factor = max(0.25, min(4.0, float(threshold) * 10.0))
    margin = max(1, int(margin_base * factor))
    min_dist = max(1, int(min_distance_base * factor))

    # High-res guard: avoid too-dense detection on 4K+ with tiny threshold
    w, _ = clip.size
    if w >= 4000 and threshold <= 0.01:
        min_dist = max(min_dist, int(w * 0.12))
        margin = max(margin, int(w * 0.04))

    with _ensure_clip_context(ctx, clip=clip, allow_area_switch=False) as ovr:
        sd = ovr.get("space_data")
        if not sd or getattr(sd, "clip", None) is None:
            return {"status": "failed", "reason": "no_valid_clip_context"}
        try:
            res = bpy.ops.clip.detect_features(
                threshold=float(threshold),
                min_distance=int(min_dist),
                margin=int(margin),
                placement='FRAME',
            )
        except Exception as ex:
            return {"status": "failed", "reason": f"detect_features exception: {ex}"}
    return {"status": "ok", "op_result": res, "threshold": float(threshold), "margin": margin, "min_distance": min_dist}

def run_detect_once(context, *, start_frame=None):
    """
    Optionally set frame, then call adaptive detection.
    """
    clip = _resolve_clip_from_context(context)
    if clip is None:
        return {"status": "failed", "reason": "no_clip"}
    if start_frame is not None:
        with _ensure_clip_context(context, clip=clip, allow_area_switch=False):
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
    """
    Adaptive detection to reach [min_marker, max_marker].
    """
    scn = context.scene
    clip = _resolve_clip_from_context(context)
    if clip is None:
        return {"status": "failed", "reason": "no_clip"}
    tracking = clip.tracking
    ts = tracking.settings
    w, _ = clip.size

    # initial threshold
    thr = float(detection_threshold) if (detection_threshold is not None and detection_threshold >= 0) else float(
        scn.get("last_detection_threshold", getattr(ts, "correlation_min", 0.9))
    )
    thr = _clamp01(thr)
    scn["last_detection_threshold"] = thr

    # bounds
    adapt = int(marker_adapt) if marker_adapt >= 0 else int(scn.get("marker_adapt", scn.get("marker_basis", 20)))
    basis_for_bounds = max(1, int(adapt * 1.1))
    mn = int(min_marker) if min_marker >= 0 else int(scn.get("marker_min", int(basis_for_bounds * 0.9)))
    mx = int(max_marker) if max_marker >= 0 else int(scn.get("marker_max", int(basis_for_bounds * 1.1)))
    print(f"[Detect] Verwende min_marker={mn}, max_marker={mx} (Scene: min={scn.get('marker_min')}, max={scn.get('marker_max')})")

    # bases if not provided
    if margin_base is None or margin_base < 0:
        margin_base = max(1.0, w * 0.025)
    if min_distance_base is None or min_distance_base < 0:
        min_distance_base = max(1.0, w * 0.05)

    # remove previous newly created tracks
    prev = list(scn.get("detect_prev_names", []))
    if prev:
        names = set(prev)
        removed = 0
        for t in list(tracking.tracks):
            if t.name in names:
                try:
                    tracking.tracks.remove(t)
                    removed += 1
                except Exception:
                    pass
        if removed:
            print(f"[Detect] Entfernt {removed} alte 'detect_prev_names'-Tracks")
        scn["detect_prev_names"] = []

    attempt = 0
    while attempt < int(max_attempts):
        current_frame = int(scn.frame_current)
        # snapshot existing names
        initial_names = [t.name for t in tracking.tracks]
        # detect
        det_res = perform_marker_detection(context, clip, tracking, thr, margin_base, min_distance_base)
        if det_res.get("status") != "ok":
            return {"status": "failed", "reason": det_res.get("reason", "detect_failed")}
        # small wait for datablock updates
        waited = 0
        while waited < 50:
            if len(tracking.tracks) != len(initial_names):
                break
            time.sleep(0.01)
            waited += 1

        # collect new tracks
        new_tracks = [t for t in tracking.tracks if t.name not in initial_names]

        # filter too-close tracks
        def _collect_positions(frame):
            pos = []
            for t in tracking.tracks:
                mk = t.markers.find_frame(frame)
                if mk:
                    x = mk.co[0] * w
                    y = mk.co[1] * _  # h, but unused for distance scale
                    pos.append((x, y))
            return pos
        existing_positions = _collect_positions(current_frame)
        close_thr2 = (max(1.0, w * float(close_dist_rel))) ** 2
        close_names = []
        for t in new_tracks:
            mk = t.markers.find_frame(current_frame)
            if not mk:
                continue
            px = mk.co[0] * w
            py = mk.co[1] * _
            if any((px - ex)**2 + (py - ey)**2 < close_thr2 for (ex, ey) in existing_positions):
                close_names.append(t.name)
        if close_names:
            cnt = 0
            for t in list(tracking.tracks):
                if t.name in close_names:
                    try:
                        tracking.tracks.remove(t)
                        cnt += 1
                    except Exception:
                        pass
            if cnt:
                print(f"[Detect] Entfernte {cnt} nahe/doppelte Tracks")

        cleaned_tracks = [t for t in tracking.tracks if (t.name not in initial_names) and (t.name not in close_names)]
        num_new = len(cleaned_tracks)

        if num_new < mn or num_new > mx:
            # remove newly created and adapt threshold
            names_to_remove = [t.name for t in cleaned_tracks]
            for nm in names_to_remove:
                try:
                    tracking.tracks.remove(tracking.tracks[nm])
                except Exception:
                    # fall back: linear search
                    for t in list(tracking.tracks):
                        if t.name == nm:
                            try:
                                tracking.tracks.remove(t)
                            except Exception:
                                pass
                            break
            scale = max(0.1, (num_new + 0.1) / max(1.0, float(adapt)))
            thr = _clamp01(thr * scale)
            scn["last_detection_threshold"] = thr
            attempt += 1
            continue

        scn["detect_prev_names"] = [t.name for t in cleaned_tracks]
        if handoff_to_pipeline:
            scn["detect_status"] = "success"
            scn["pipeline_do_not_start"] = False
        else:
            scn["detect_status"] = "standalone_success"
            scn["pipeline_do_not_start"] = True

        return {"status": "success", "attempts": attempt + 1, "new_tracks": num_new, "threshold": thr}

    scn["detect_status"] = "failed"
    return {"status": "failed", "attempts": attempt, "threshold": thr}
