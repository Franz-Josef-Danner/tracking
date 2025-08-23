from __future__ import annotations

"""
Helper/detect.py — Extended feature detection for Blender's Movie Clip Editor.

Highlights
----------
- Backward compatible public API (perform_marker_detection, run_detect_once, run_detect_adaptive)
- Optional ROI post-filter (normalized [0..1] rect or pixel rect)
- KD‑Tree based near‑duplicate removal (faster for many markers)
- Corridor control with smooth PID‑like threshold adaption (stable convergence)
- Selection policy (leave/only_new/restore)
- Duplicate cleanup strategy (delete/mute/tag)
- Optional track tagging prefix for newly created tracks
- Dry‑run mode (executes detect and cleans everything it created)
- Rich result object with metrics
- NEW: Pattern-triplet post step with name aggregation & selection (0.8× / 1.2×)

Blender ≥ 3.0 assumed (mathutils.KDTree available).
"""

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import bpy
from mathutils.kdtree import KDTree

__all__ = [
    "perform_marker_detection",
    "run_detect_once",
    "run_detect_adaptive",
]

# ---------------------------------------------------------------------
# Scene keys / state
# ---------------------------------------------------------------------
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # float
_LOCK_KEY = "__detect_lock"
_PREV_SEL_KEY = "__detect_prev_selection"

# ---------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------

@dataclass
class DetectMetrics:
    frame: int
    requested_threshold: float
    applied_threshold: float
    margin_px: int
    min_distance_px: int
    tracks_before: int
    tracks_new_raw: int
    tracks_near_dupe: int
    tracks_new_clean: int
    roi_rejected: int
    duration_ms: float


# ---------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------

def _find_clip_editor_context():
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return window, area, region, space
    return None, None, None, None


def _run_in_clip_context(op_callable, **kwargs):
    window, area, region, space = _find_clip_editor_context()
    if not (window and area and region and space):
        print("[DetectTrace] No CLIP_EDITOR context found – running operator without override.")
        return op_callable(**kwargs)
    override = {
        "window": window,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    with bpy.context.temp_override(**override):
        return op_callable(**kwargs)


def _get_movieclip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    if mc:
        return mc
    for c in bpy.data.movieclips:
        return c
    return None

# ---------------------------------------------------------------------
# Track helpers
# ---------------------------------------------------------------------

def _deselect_all(tracking: bpy.types.MovieTracking) -> None:
    for t in tracking.tracks:
        t.select = False


def _delete_selected_tracks(confirm: bool = True) -> None:
    def _op(**kw):
        return bpy.ops.clip.delete_track(**kw)

    _run_in_clip_context(_op, confirm=confirm)


def _collect_positions_at_frame(
    tracks: Iterable[bpy.types.MovieTrackingTrack], frame: int, w: int, h: int
) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for t in tracks:
        try:
            m = t.markers.find_frame(frame, exact=True)
        except TypeError:
            m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            out.append((m.co[0] * w, m.co[1] * h))
    return out


# ---------------------------------------------------------------------
# Geometry / ROI
# ---------------------------------------------------------------------

def _normalize_roi(
    roi: Optional[Tuple[float, float, float, float]], width: int, height: int
) -> Optional[Tuple[int, int, int, int]]:
    """Return pixel ROI (x, y, w, h) or None. Accepts normalized [0..1] or pixel tuple."""
    if not roi:
        return None
    x, y, w, h = roi
    # Heuristic: values > 1 are pixels
    if max(abs(x), abs(y), abs(w), abs(h)) <= 1.0:
        return (
            int(max(0, round(x * width))),
            int(max(0, round(y * height))),
            int(max(1, round(w * width))),
            int(max(1, round(h * height))),
        )
    return (int(x), int(y), int(w), int(h))


def _inside_roi(px: float, py: float, roi_px: Tuple[int, int, int, int]) -> bool:
    x, y, w, h = roi_px
    return (x <= px <= x + w) and (y <= py <= y + h)


# ---------------------------------------------------------------------
# Core ops
# ---------------------------------------------------------------------

def _scaled_params(threshold: float, margin_base: int, min_distance_base: int) -> Tuple[int, int]:
    factor = math.log10(max(float(threshold), 1e-6) * 1e6) / 6.0
    margin = max(1, int(int(margin_base) * factor))
    min_distance = max(1, int(int(min_distance_base) * factor))
    return margin, min_distance


def perform_marker_detection(
    clip: bpy.types.MovieClip,
    tracking: bpy.types.MovieTracking,
    threshold: float,
    margin_base: int,
    min_distance_base: int,
) -> int:
    margin, min_distance = _scaled_params(float(threshold), int(margin_base), int(min_distance_base))

    def _op(**kw):
        try:
            return bpy.ops.clip.detect_features(**kw)
        except TypeError:
            return bpy.ops.clip.detect_features()

    print(
        f"[DetectTrace] detect_features: thr={threshold:.6f}, margin={margin}, min_dist={min_distance}"
    )
    t0 = time.perf_counter()
    try:
        _run_in_clip_context(
            _op,
            margin=int(margin),
            min_distance=int(min_distance),
            threshold=float(threshold),
        )
    except Exception as ex:
        dt = (time.perf_counter() - t0) * 1000.0
        print(f"[DetectError] detect_features Exception ({dt:.1f} ms): {ex}")
        raise
    dt = (time.perf_counter() - t0) * 1000.0
    print(f"[DetectTrace] detect_features DONE in {dt:.1f} ms")
    return sum(1 for t in tracking.tracks if getattr(t, "select", False))


# ---------------------------------------------------------------------
# Pattern-triplet helpers & API
# ---------------------------------------------------------------------

def _collect_track_pointers(tracks: Iterable[bpy.types.MovieTrackingTrack]) -> Set[int]:
    return {t.as_pointer() for t in tracks}


def _collect_new_track_names_by_pointer(
    tracks: Iterable[bpy.types.MovieTrackingTrack], before_ptrs: Set[int]
) -> List[str]:
    return [t.name for t in tracks if t.as_pointer() not in before_ptrs]


def _select_tracks_by_names(tracking: bpy.types.MovieTracking, names: Set[str]) -> int:
    count = 0
    for t in tracking.tracks:
        sel = t.name in names
        t.select = sel
        if sel:
            count += 1
    return count


def _set_pattern_size(tracking: bpy.types.MovieTracking, new_size: int) -> int:
    s = tracking.settings
    clamped = max(3, min(101, int(new_size)))  # conservative bounds
    try:
        s.default_pattern_size = clamped
    except Exception:
        pass
    return int(getattr(s, "default_pattern_size", clamped))


def _get_pattern_size(tracking: bpy.types.MovieTracking) -> int:
    try:
        return int(tracking.settings.default_pattern_size)
    except Exception:
        return 15


def run_pattern_triplet_and_select_by_name(
    context: bpy.types.Context,
    *,
    scale_low: float = 0.5,
    scale_high: float = 1.5,
    also_include_ready_selection: bool = True,
    adjust_search_with_pattern: bool = False,
    # NEU:
    detect_threshold: Optional[float] = None,
    detect_margin: Optional[int] = None,
    detect_min_distance: Optional[int] = None,
) -> Dict[str, Any]:
    """Runs two extra detect sweeps with scaled pattern size and selects all newly created
    markers by NAME (aggregated across both sweeps, optionally including current selection).
    """
    clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)
    if not clip:
        print("[PatternTriplet] No MovieClip available.")
        return {"status": "FAILED", "reason": "no_movieclip"}
    
    tracking = clip.tracking
    settings = tracking.settings
    
    pattern_o = _get_pattern_size(tracking)
    search_o = int(getattr(settings, "default_search_size", max(5, pattern_o * 2)))
    aggregated_names: Set[str] = set()
    
    if also_include_ready_selection:
        for t in tracking.tracks:
            if getattr(t, "select", False):
                aggregated_names.add(t.name)
    
    def sweep(scale: float) -> int:
        before_ptrs = _collect_track_pointers(tracking.tracks)
    
        # neues Pattern setzen
        new_pattern = max(3, int(round(pattern_o * float(scale))))
        _set_pattern_size(tracking, new_pattern)
    
        # NEU: Search-Size = 2 × aktuelles Pattern
        try:
            settings.default_search_size = max(5, new_pattern * 2)
        except Exception:
            pass
    
        # detect_features mit identischen Parametern wie im READY-Pass
        def _op(**kw):
            return bpy.ops.clip.detect_features(**kw)
    
        kw = {}
        if detect_threshold is not None:    kw["threshold"] = float(detect_threshold)
        if detect_margin is not None:       kw["margin"] = int(detect_margin)
        if detect_min_distance is not None: kw["min_distance"] = int(detect_min_distance)
    
        try:
            _run_in_clip_context(_op, **kw)
        except Exception as ex:
            print(f"[PatternTriplet] detect_features Exception @scale={scale}: {ex}")
    
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass
    
        new_names = _collect_new_track_names_by_pointer(tracking.tracks, before_ptrs)
        aggregated_names.update(new_names)
        return len(new_names)
    
    # Sweeps ausführen
    created_low = sweep(scale_low)
    created_high = sweep(scale_high)
    
    # --- Rückstellung NACH den Sweeps (einmalig) ---
    _set_pattern_size(tracking, pattern_o)
    try:
        # Konsistenz: Search-Size zurück auf 2 × ursprüngliches Pattern
        settings.default_search_size = max(5, pattern_o * 2)
    except Exception:
        pass


    for t in tracking.tracks:
        t.select = False
    selected = _select_tracks_by_names(tracking, aggregated_names)

    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass

    print(
        f"[PatternTriplet] DONE | pattern_o={pattern_o} | low={scale_low} -> +{created_low} | "
        f"high={scale_high} -> +{created_high} | selected_by_name={selected}"
    )

    return {
        "status": "READY",
        "created_low": int(created_low),
        "created_high": int(created_high),
        "selected": int(selected),
        "names": sorted(aggregated_names),
    }


# ---------------------------------------------------------------------
# Public: one detect pass
# ---------------------------------------------------------------------

def run_detect_once(
    context: bpy.types.Context,
    *,
    start_frame: Optional[int] = None,
    threshold: Optional[float] = None,
    marker_adapt: Optional[int] = None,
    min_marker: Optional[int] = None,
    max_marker: Optional[int] = None,
    margin_base: Optional[int] = None,
    min_distance_base: Optional[int] = None,
    close_dist_rel: float = 0.01,
    handoff_to_pipeline: bool = False,
    # --- extended options ---
    selection_policy: str = "only_new",  # "leave"|"only_new"|"restore"
    duplicate_strategy: str = "delete",  # "delete"|"mute"|"tag"
    duplicate_tag: str = "NEAR_DUP",
    tag_prefix: Optional[str] = None,
    roi: Optional[Tuple[float, float, float, float]] = None,
    dry_run: bool = False,
    # --- NEW: post pattern-triplet ---
    post_pattern_triplet: bool = False,
    triplet_scale_low: float = 0.8,
    triplet_scale_high: float = 1.2,
    triplet_include_ready_selection: bool = True,
    triplet_adjust_search_with_pattern: bool = False,
) -> Dict[str, Any]:
    """Execute one detection round with optional ROI/duplicate clean and optional
    post pattern‑triplet step which aggregates names and selects them.
    """
    scn = context.scene
    if scn.get(_LOCK_KEY):
        print("[DetectWarn] Reentrancy prevented – lock is held.")
        return {"status": "FAILED", "reason": "locked"}

    scn[_LOCK_KEY] = True

    frame: int = int(getattr(scn, "frame_current", 0))
    before_ids: set[int] = set()
    new_tracks_raw: List[bpy.types.MovieTrackingTrack] = []
    near_dupes: List[bpy.types.MovieTrackingTrack] = []
    cleaned: List[bpy.types.MovieTrackingTrack] = []

    prev_selection: List[int] = []

    try:
        clip = _get_movieclip(context)
        if not clip:
            print("[DetectError] No MovieClip available.")
            return {"status": "FAILED", "reason": "no_movieclip"}

        tracking = clip.tracking
        width, height = int(clip.size[0]), int(clip.size[1])

        # Frame set
        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
            except Exception as ex:
                print(f"[DetectError] frame_set({start_frame}) Exception: {ex}")
        frame = int(scn.frame_current)

        # Threshold
        if threshold is None:
            base_thr = float(getattr(tracking.settings, "default_correlation_min", 0.75))
            try:
                last_thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, base_thr))
            except Exception:
                last_thr = base_thr
            threshold = max(1e-6, float(last_thr))
        else:
            threshold = max(1e-6, float(threshold))

        # Corridor
        if marker_adapt is None:
            try:
                marker_adapt = int(scn.get("marker_adapt", scn.get("marker_basis", 20)))
            except Exception:
                marker_adapt = int(scn.get("marker_basis", 20))
        safe_adapt = max(1, int(marker_adapt))
        if min_marker is None:
            min_marker = int(max(1, round(safe_adapt * 0.9)))
        if max_marker is None:
            max_marker = int(max(2, round(safe_adapt * 1.2)))

        # Bases
        if margin_base is None:
            margin_base = max(1, int(width * 0.025))
        if min_distance_base is None:
            min_distance_base = max(1, int(width * 0.05))

        roi_px = _normalize_roi(roi, width, height)

        print(
            "[DetectTrace] START "
            f"| frame={frame} | thr_in={threshold:.6f} | adapt={safe_adapt} "
            f"| corridor=[{min_marker}..{max_marker}] | bases: margin={margin_base}, min_dist={min_distance_base} "
            f"| roi={'none' if roi_px is None else roi_px} | selection={selection_policy} | dup={duplicate_strategy}"
        )

        # Save previous selection if needed
        if selection_policy == "restore":
            prev_selection = [t.as_pointer() for t in tracking.tracks if getattr(t, "select", False)]
            scn[_PREV_SEL_KEY] = prev_selection

        before_ids = {t.as_pointer() for t in tracking.tracks}
        existing_px = _collect_positions_at_frame(tracking.tracks, frame, width, height)

        # Detect
        _deselect_all(tracking)
        try:
            perform_marker_detection(clip, tracking, float(threshold), int(margin_base), int(min_distance_base))
        except Exception as ex:
            print("[DetectError] detect_features op FAILED:", ex)
            try:
                scn["detect_status"] = "failed"
            except Exception:
                pass
            return {"status": "FAILED", "reason": "detect_features_failed", "frame": int(frame)}

        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

        # Gather new tracks
        tracks_list = list(tracking.tracks)
        new_tracks_raw = [t for t in tracks_list if t.as_pointer() not in before_ids]

        # Optional tagging
        if tag_prefix:
            for t in new_tracks_raw:
                try:
                    t.name = f"{tag_prefix}_{t.name}"
                except Exception:
                    pass

        # Near-duplicate detection (KDTree)
        distance_px = max(1, int(width * (close_dist_rel if close_dist_rel > 0 else 0.01)))
        thr2 = float(distance_px * distance_px)

        near_dupes = []
        if existing_px and new_tracks_raw:
            tree = KDTree(len(existing_px))
            for i, (ex, ey) in enumerate(existing_px):
                tree.insert((ex, ey, 0.0), i)
            tree.balance()
            for tr in new_tracks_raw:
                try:
                    m = tr.markers.find_frame(frame, exact=True)
                except TypeError:
                    m = tr.markers.find_frame(frame)
                if m and not getattr(m, "mute", False):
                    x = m.co[0] * width
                    y = m.co[1] * height
                    (loc, _idx, _dist) = tree.find((x, y, 0.0))
                    dx = x - loc[0]
                    dy = y - loc[1]
                    if (dx * dx + dy * dy) < thr2:
                        near_dupes.append(tr)

        # ROI post-filter
        roi_rejected: List[bpy.types.MovieTrackingTrack] = []
        if roi_px is not None and new_tracks_raw:
            for tr in new_tracks_raw:
                try:
                    m = tr.markers.find_frame(frame, exact=True)
                except TypeError:
                    m = tr.markers.find_frame(frame)
                if not m or getattr(m, "mute", False):
                    continue
                px = m.co[0] * width
                py = m.co[1] * height
                if not _inside_roi(px, py, roi_px):
                    roi_rejected.append(tr)

        # Combine rejects (dupes ∪ roi)
        reject_set = {t.as_pointer() for t in near_dupes}
        reject_set.update(t.as_pointer() for t in roi_rejected)

        _deselect_all(tracking)
        for t in new_tracks_raw:
            if t.as_pointer() in reject_set:
                if duplicate_strategy == "mute":
                    t.mute = True
                elif duplicate_strategy == "tag":
                    try:
                        t.name = f"NEAR_DUP_{t.name}" if duplicate_tag == "NEAR_DUP" else f"{duplicate_tag}_{t.name}"
                    except Exception:
                        pass
                t.select = True
        if any(t.select for t in tracking.tracks):
            try:
                if duplicate_strategy == "delete":
                    _delete_selected_tracks(confirm=True)
            except Exception as ex:
                print(f"[DetectError] delete_track failed, fallback remove: {ex}")
                for t in list(tracking.tracks):
                    if getattr(t, "select", False):
                        try:
                            tracking.tracks.remove(t)
                        except Exception:
                            pass

        cleaned = [t for t in new_tracks_raw if t.as_pointer() not in reject_set]

        # Dry-run? Remove all new tracks
        if dry_run and cleaned:
            _deselect_all(tracking)
            for t in cleaned:
                t.select = True
            try:
                _delete_selected_tracks(confirm=True)
            except Exception:
                for t in list(cleaned):
                    try:
                        tracking.tracks.remove(t)
                    except Exception:
                        pass
            cleaned = []

        # Selection handling
        _deselect_all(tracking)
        if selection_policy == "only_new":
            for t in cleaned:
                t.select = True
        elif selection_policy == "restore":
            prev = scn.get(_PREV_SEL_KEY, []) or prev_selection
            ptrs = set(prev)
            for t in tracking.tracks:
                t.select = t.as_pointer() in ptrs

        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

        # Corridor logic
        new_count = len(cleaned)
        if new_count < int(min_marker) or new_count > int(max_marker):
            # Remove what we added in this run so the next attempt starts clean
            if cleaned:
                _deselect_all(tracking)
                for t in cleaned:
                    t.select = True
                try:
                    _delete_selected_tracks(confirm=True)
                except Exception as ex:
                    print(f"[DetectError] delete_track on corridor-miss: {ex}")
                    for t in list(cleaned):
                        try:
                            tracking.tracks.remove(t)
                        except Exception:
                            pass

            # PID-like adjustment (P + mild I)
            target = float(max(1, int(marker_adapt or new_count)))
            error = (float(new_count) - target) / max(target, 1.0)
            k_p = 0.65
            k_i = 0.10
            acc = float(scn.get("__thr_i", 0.0)) + error
            scn["__thr_i"] = acc
            scale = 1.0 + (k_p * error + k_i * acc)
            new_threshold = max(1e-4, float(threshold) * scale)

            try:
                scn[DETECT_LAST_THRESHOLD_KEY] = float(new_threshold)
                scn["detect_status"] = "running"
            except Exception:
                pass

            print(
                "[DetectDebug] RUNNING → new_threshold=%.6f (old=%.6f, adapt=%d) | new=%d | corridor=[%d..%d]"
                % (
                    float(new_threshold),
                    float(threshold),
                    int(marker_adapt or target),
                    int(new_count),
                    int(min_marker),
                    int(max_marker),
                )
            )

            metrics = DetectMetrics(
                frame=frame,
                requested_threshold=float(threshold),
                applied_threshold=float(threshold),
                margin_px=int(max(1, int(width * 0.025) if margin_base is None else margin_base)),
                min_distance_px=int(max(1, int(width * 0.05) if min_distance_base is None else min_distance_base)),
                tracks_before=len(before_ids),
                tracks_new_raw=len(new_tracks_raw),
                tracks_near_dupe=len(near_dupes),
                tracks_new_clean=new_count,
                roi_rejected=len(roi_rejected),
                duration_ms=0.0,
            )
            return {
                "status": "RUNNING",
                "new_tracks": int(new_count),
                "threshold": float(new_threshold),
                "frame": int(frame),
                "metrics": metrics.__dict__,
            }

        # READY: success → remember threshold and optionally run pattern-triplet
        try:
            scn[DETECT_LAST_THRESHOLD_KEY] = float(threshold)
        except Exception:
            pass

        try:
            if handoff_to_pipeline:
                scn["detect_status"] = "success"
                scn["pipeline_do_not_start"] = False
            else:
                scn["detect_status"] = "standalone_success"
                scn["pipeline_do_not_start"] = True
        except Exception:
            pass

        print(
            "[DetectDebug] READY | new=%d in corridor [%d..%d] | threshold_keep=%.6f"
            % (int(new_count), int(min_marker), int(max_marker), float(threshold))
        )

        # ---- NEW: invoke pattern-triplet if requested ----
        triplet_result: Optional[Dict[str, Any]] = None
        if post_pattern_triplet:
            try:
                # identische detect-Parameter berechnen wie im READY-Pass verwendet:
                margin_applied, min_dist_applied = _scaled_params(float(threshold),
                                                                  int(margin_base),
                                                                  int(min_distance_base))
                triplet_result = run_pattern_triplet_and_select_by_name(
                    context,
                    scale_low=float(triplet_scale_low),
                    scale_high=float(triplet_scale_high),
                    also_include_ready_selection=bool(triplet_include_ready_selection),
                    adjust_search_with_pattern=bool(triplet_adjust_search_with_pattern),
                    # NEU: festnageln
                    detect_threshold=float(threshold),
                    detect_margin=int(margin_applied),
                    detect_min_distance=int(min_dist_applied),
                )

                print(f"[DetectTrace] Post pattern-triplet result: {triplet_result}")
            except Exception as ex:
                print(f"[DetectError] pattern-triplet failed: {ex}")

        metrics = DetectMetrics(
            frame=frame,
            requested_threshold=float(threshold),
            applied_threshold=float(threshold),
            margin_px=int(max(1, int(width * 0.025) if margin_base is None else margin_base)),
            min_distance_px=int(max(1, int(width * 0.05) if min_distance_base is None else min_distance_base)),
            tracks_before=len(before_ids),
            tracks_new_raw=len(new_tracks_raw),
            tracks_near_dupe=len(near_dupes),
            tracks_new_clean=len(cleaned),
            roi_rejected=len(roi_rejected),
            duration_ms=0.0,
        )

        result: Dict[str, Any] = {
            "status": "READY",
            "new_tracks": int(new_count),
            "threshold": float(threshold),
            "frame": int(frame),
            "metrics": metrics.__dict__,
        }
        if triplet_result is not None:
            result["post_pattern_triplet"] = triplet_result

        return result

    except Exception as ex:
        print("[DetectError] FAILED:", ex)
        try:
            scn["detect_status"] = "failed"
        except Exception:
            pass
        return {"status": "FAILED", "reason": str(ex), "frame": int(frame)}
    finally:
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass


# ---------------------------------------------------------------------
# Public: adaptive loop
# ---------------------------------------------------------------------

def run_detect_adaptive(
    context: bpy.types.Context,
    *,
    start_frame: Optional[int] = None,
    max_attempts: int = 8,
    **kwargs,
) -> Dict[str, Any]:
    last: Dict[str, Any] = {}
    for attempt in range(max_attempts):
        print(f"[DetectTrace] ADAPTIVE attempt {attempt + 1}/{max_attempts}")
        last = run_detect_once(context, start_frame=start_frame, **kwargs)
        st = last.get("status")
        if st in ("READY", "FAILED"):
            print(f"[DetectTrace] ADAPTIVE STOP status={st}")
            return last
        start_frame = last.get("frame", start_frame)
    print("[DetectTrace] ADAPTIVE max_attempts_exceeded")
    return last or {"status": "FAILED", "reason": "max_attempts_exceeded"}
