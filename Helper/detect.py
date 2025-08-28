from __future__ import annotations

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
    if not roi:
        return None
    x, y, w, h = roi
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

    t0 = time.perf_counter()
    _run_in_clip_context(
        _op,
        margin=int(margin),
        min_distance=int(min_distance),
        threshold=float(threshold),
    )
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
    clamped = max(3, min(101, int(new_size)))
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
    scale_high: float = 2,
    also_include_ready_selection: bool = True,
    adjust_search_with_pattern: bool = False,
    detect_threshold: Optional[float] = None,
    detect_margin: Optional[int] = None,
    detect_min_distance: Optional[int] = None,
    close_dist_rel: float = 0.01,
    pre_detect_ptrs: Optional[Set[int]] = None,
    pre_detect_kdtree: Optional[KDTree] = None,
    pre_frame: Optional[int] = None,
    pre_size: Optional[Tuple[int, int]] = None,
) -> Dict[str, Any]:
    clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)
    if not clip:
        for c in bpy.data.movieclips:
            clip = c
            break
    if not clip:
        return {"status": "FAILED", "reason": "no_movieclip"}

    tracking = clip.tracking
    settings = tracking.settings
    scn = context.scene

    try:
        frame_now = int(getattr(scn, "frame_current", 0))
    except Exception:
        frame_now = 0
    width, height = int(clip.size[0]), int(clip.size[1])

    kd_tree = pre_detect_kdtree
    if pre_detect_ptrs is not None:
        base_ptrs: Set[int] = set(pre_detect_ptrs)
        if kd_tree is None and pre_size is not None and pre_frame is not None:
            _w, _h = pre_size
            existing_px = _collect_positions_at_frame(
                [t for t in tracking.tracks if t.as_pointer() in base_ptrs], int(pre_frame), _w, _h
            )
            if existing_px:
                kd_tree = KDTree(len(existing_px))
                for i, (ex, ey) in enumerate(existing_px):
                    kd_tree.insert((ex, ey, 0.0), i)
                kd_tree.balance()
    else:
        base_ptrs = _collect_track_pointers(tracking.tracks)
        existing_px = _collect_positions_at_frame(tracking.tracks, frame_now, width, height)
        if existing_px:
            kd_tree = KDTree(len(existing_px))
            for i, (ex, ey) in enumerate(existing_px):
                kd_tree.insert((ex, ey, 0.0), i)
            kd_tree.balance()

    pattern_o = _get_pattern_size(tracking)
    aggregated_names: Set[str] = set()

    if also_include_ready_selection:
        for t in tracking.tracks:
            if getattr(t, "select", False):
                aggregated_names.add(t.name)

    def sweep(scale: float) -> int:
        before_ptrs = _collect_track_pointers(tracking.tracks)
        new_pattern = max(3, int(round(pattern_o * float(scale))))
        eff = _set_pattern_size(tracking, new_pattern)
        try:
            settings.default_search_size = max(5, eff * 2)
        except Exception:
            pass

        def _op(**kw):
            return bpy.ops.clip.detect_features(**kw)

        kw = {}
        if detect_threshold is not None:
            kw["threshold"] = float(detect_threshold)
        if detect_margin is not None:
            kw["margin"] = int(detect_margin)
        if detect_min_distance is not None:
            kw["min_distance"] = int(detect_min_distance)

        _run_in_clip_context(_op, **kw)

        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

        new_names = _collect_new_track_names_by_pointer(tracking.tracks, before_ptrs)
        aggregated_names.update(new_names)
        return len(new_names)

    created_low = sweep(scale_low)
    created_high = sweep(scale_high)

    _set_pattern_size(tracking, pattern_o)
    try:
        settings.default_search_size = pattern_o * 2
    except Exception:
        pass

    distance_px = max(1, int(width * (close_dist_rel if close_dist_rel > 0 else 0.01)))
    thr2 = float(distance_px * distance_px)

    triplet_new_tracks = [t for t in tracking.tracks if t.as_pointer() not in base_ptrs]

    reject_ptrs: Set[int] = set()
    if kd_tree and triplet_new_tracks:
        for tr in triplet_new_tracks:
            try:
                m = tr.markers.find_frame(frame_now, exact=True)
            except TypeError:
                m = tr.markers.find_frame(frame_now)
            if not m or getattr(m, "mute", False):
                continue
            x = m.co[0] * width
            y = m.co[1] * height
            (loc, _idx, _dist) = kd_tree.find((x, y, 0.0))
            dx = x - loc[0]
            dy = y - loc[1]
            if (dx * dx + dy * dy) < thr2:
                reject_ptrs.add(tr.as_pointer())

    if reject_ptrs:
        _deselect_all(tracking)
        for t in triplet_new_tracks:
            if t.as_pointer() in reject_ptrs:
                t.select = True
        try:
            _delete_selected_tracks(confirm=True)
        except Exception:
            for t in list(tracking.tracks):
                if t.as_pointer() in reject_ptrs:
                    try:
                        tracking.tracks.remove(t)
                    except Exception:
                        pass

    remaining_triplet_names = {t.name for t in tracking.tracks if t.as_pointer() not in base_ptrs}
    for t in tracking.tracks:
        t.select = False
    selected = _select_tracks_by_names(tracking, remaining_triplet_names)

    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass

    return {
        "status": "READY",
        "created_low": int(created_low),
        "created_high": int(created_high),
        "rejected_vs_existing": int(len(reject_ptrs)),
        "selected": int(selected),
        "names": sorted(remaining_triplet_names),
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
    selection_policy: str = "only_new",
    duplicate_strategy: str = "delete",
    duplicate_tag: str = "NEAR_DUP",
    tag_prefix: Optional[str] = None,
    roi: Optional[Tuple[float, float, float, float]] = None,
    dry_run: bool = False,
    post_pattern_triplet=True,
    triplet_scale_low: float = 0.5,
    triplet_scale_high: float = 2,
    triplet_include_ready_selection: bool = True,
    triplet_adjust_search_with_pattern: bool = False,
) -> Dict[str, Any]:
    scn = context.scene
    if scn.get(_LOCK_KEY):
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
            return {"status": "FAILED", "reason": "no_movieclip"}

        tracking = clip.tracking
        width, height = int(clip.size[0]), int(clip.size[1])

        if start_frame is not None:
            try:
                scn.frame_set(int(start_frame))
            except Exception:
                pass
        frame = int(scn.frame_current)

        if threshold is None:
            base_thr = float(getattr(tracking.settings, "default_correlation_min", 0.75))
            try:
                last_thr = float(scn.get(DETECT_LAST_THRESHOLD_KEY, base_thr))
            except Exception:
                last_thr = base_thr
            threshold = max(1e-6, float(last_thr))
        else:
            threshold = max(1e-6, float(threshold))

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

        if margin_base is None:
            margin_base = max(1, int(width * 0.025))
        if min_distance_base is None:
            min_distance_base = max(1, int(width * 0.05))

        roi_px = _normalize_roi(roi, width, height)

        if selection_policy == "restore":
            prev_selection = [t.as_pointer() for t in tracking.tracks if getattr(t, "select", False)]
            scn[_PREV_SEL_KEY] = prev_selection

        before_ids = {t.as_pointer() for t in tracking.tracks}
        existing_px = _collect_positions_at_frame(tracking.tracks, frame, width, height)
        pre_kd: Optional[KDTree] = None
        if existing_px:
            pre_kd = KDTree(len(existing_px))
            for i, (ex, ey) in enumerate(existing_px):
                pre_kd.insert((ex, ey, 0.0), i)
            pre_kd.balance()

        _deselect_all(tracking)
        perform_marker_detection(clip, tracking, float(threshold), int(margin_base), int(min_distance_base))

        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

        tracks_list = list(tracking.tracks)
        new_tracks_raw = [t for t in tracks_list if t.as_pointer() not in before_ids]

        if tag_prefix:
            for t in new_tracks_raw:
                try:
                    t.name = f"{tag_prefix}_{t.name}"
                except Exception:
                    pass

        distance_px = max(1, int(width * (close_dist_rel if close_dist_rel > 0 else 0.01)))
        thr2 = float(distance_px * distance_px)

        near_dupes = []
        if existing_px and new_tracks_raw and pre_kd:
            for tr in new_tracks_raw:
                try:
                    m = tr.markers.find_frame(frame, exact=True)
                except TypeError:
                    m = tr.markers.find_frame(frame)
                if m and not getattr(m, "mute", False):
                    x = m.co[0] * width
                    y = m.co[1] * height
                    (loc, _idx, _dist) = pre_kd.find((x, y, 0
