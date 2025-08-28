# Helper/projektion_spike_filter_cycle.py
# SPDX-License-Identifier: MIT
from __future__ import annotations
"""
Projection-guided Spike-Filter:
- Nimmt Track-Namen aus scene['tco_proj_spike_tracks'] entgegen.
- Führt Spike-Deletion **nur** in diesen Tracks aus.
- Optional: segmentweises Cleanup via clean_short_segments.
- Protokolliert gelöschte Marker („track@frame“) in scene['tco_proj_spike_deleted_markers'].
"""

from typing import Optional, Dict, Any, List, Tuple, Iterable
import bpy
import math

__all__ = ["run_projection_spike_filter_cycle"]

_STORE_TRACKS_KEY = "tco_proj_spike_tracks"
_STORE_DELETED_KEY = "tco_proj_spike_deleted_markers"

# optionales Cleanup
try:
    from .clean_short_segments import clean_short_segments  # type: ignore
except Exception:
    clean_short_segments = None

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None

def _iter_tracks(clip: Optional[bpy.types.MovieClip]) -> Iterable[bpy.types.MovieTrackingTrack]:
    if not clip:
        return []
    try:
        for obj in clip.tracking.objects:
            for t in obj.tracks:
                yield t
    except Exception:
        return []

def _to_pixel(vec01, size_xy) -> Tuple[float, float]:
    return float(vec01[0]) * float(size_xy[0]), float(vec01[1]) * float(size_xy[1])

def _collect_frame_velocities_whitelist(
    clip: bpy.types.MovieClip,
    allowed_names: set[str],
) -> Dict[int, List[Tuple[bpy.types.MovieTrackingTrack,
                          bpy.types.MovieTrackingMarker,
                          bpy.types.MovieTrackingMarker,
                          Tuple[float, float]]]]:
    """
    Wie im Spike-Filter-Vorbild, aber beschränkt auf Tracks aus allowed_names.
    """
    result: Dict[int, List[Tuple[bpy.types.MovieTrackingTrack,
                                 bpy.types.MovieTrackingMarker,
                                 bpy.types.MovieTrackingMarker,
                                 Tuple[float, float]]]] = {}
    size = getattr(clip, "size", (1.0, 1.0))

    # schneller Lookup
    allowed = allowed_names

    for tr in _iter_tracks(clip):
        if tr.name not in allowed:
            continue
        markers: List[bpy.types.MovieTrackingMarker] = list(tr.markers)
        if len(markers) < 2:
            continue

        prev = markers[0]
        for i in range(1, len(markers)):
            curr = markers[i]
            if getattr(curr, "mute", False) or getattr(prev, "mute", False):
                prev = curr
                continue

            f0 = int(getattr(prev, "frame", -10))
            f1 = int(getattr(curr, "frame", -10))
            dt = f1 - f0
            if dt <= 0:
                prev = curr
                continue

            x0, y0 = _to_pixel(prev.co, size)
            x1, y1 = _to_pixel(curr.co, size)
            vx = (x1 - x0) / float(dt)
            vy = (y1 - y0) / float(dt)

            result.setdefault(f1, []).append((tr, prev, curr, (vx, vy)))
            prev = curr

    return result

# ------------------------------------------------------------
# Öffentliche API
# ------------------------------------------------------------
def run_projection_spike_filter_cycle(
    context: bpy.types.Context,
    *,
    track_threshold: float = 2.0,  # Pixel/Frame
    run_segment_cleanup: bool = True,
    min_segment_len: Optional[int] = None,
    treat_muted_as_gap: bool = True,
) -> Dict[str, Any]:
    """
    Löscht Spike-Marker **nur** in den Tracks aus scene['tco_proj_spike_tracks'].
    Persistiert gelöschte Marker in scene['tco_proj_spike_deleted_markers'].
    """
    clip = _active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no_active_clip"}

    scene = getattr(context, "scene", None)
    names = []
    try:
        names = list(scene.get(_STORE_TRACKS_KEY, []) or [])
    except Exception:
        names = []
    allowed = {str(n) for n in names if n}

    if not allowed:
        return {"status": "SKIPPED", "reason": "no_allowed_tracks"}

    frame_map = _collect_frame_velocities_whitelist(clip, allowed_names=allowed)
    thr = max(2.0, float(track_threshold))

    deleted = 0
    deleted_markers: List[str] = []

    for frame, entries in frame_map.items():
        if not entries:
            continue

        # v_avg
        sum_vx = sum(v[0] for _, _, _, v in entries)
        sum_vy = sum(v[1] for _, _, _, v in entries)
        inv_n = 1.0 / float(len(entries))
        v_avg = (sum_vx * inv_n, sum_vy * inv_n)

        # Kandidaten
        to_delete: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingMarker, float]] = []
        for tr, _m_prev, m_curr, v in entries:
            dvx = v[0] - v_avg[0]
            dvy = v[1] - v_avg[1]
            dev = math.hypot(dvx, dvy)
            if dev > thr:
                to_delete.append((tr, m_curr, dev))

        if not to_delete:
            continue

        for tr, m_curr, dev in reversed(to_delete):
            try:
                f = int(getattr(m_curr, "frame", -10))
                tr.markers.delete_frame(f)
                deleted += 1
                deleted_markers.append(f"{tr.name}@f{f}")
                print(f"[ProjSpike] DELETE '{tr.name}' @ f{f} |dev|={dev:.3f} > thr={thr:.3f}")
            except Exception as ex:
                print(f"[ProjSpike] DELETE failed '{tr.name}': {ex!r}")

    # Persistiere Marker-„Namen“ (Track@Frame)
    try:
        scene[_STORE_DELETED_KEY] = deleted_markers
    except Exception:
        pass

    # Optionales Segment-Cleanup
    cleaned_segments = 0
    cleaned_markers = 0
    if run_segment_cleanup and clean_short_segments is not None:
        if min_segment_len is None:
            try:
                min_segment_len = int(scene.get("tco_min_seg_len", 0)) or int(getattr(scene, "frames_track", 0)) or 25
            except Exception:
                min_segment_len = 25
        try:
            res = clean_short_segments(
                context,
                min_len=int(min_segment_len),
                treat_muted_as_gap=bool(treat_muted_as_gap),
                verbose=True,
            )
            if isinstance(res, dict):
                cleaned_segments = int(res.get("segments_removed", 0) or 0)
                cleaned_markers = int(res.get("markers_removed", 0) or 0)
        except Exception as ex:
            print(f"[ProjSpike] clean_short_segments failed: {ex!r}")

    return {
        "status": "OK",
        "deleted": int(deleted),
        "deleted_markers_key": _STORE_DELETED_KEY,
        "allowed_tracks": sorted(list(allowed)),
        "cleaned_segments": int(cleaned_segments),
        "cleaned_markers": int(cleaned_markers),
        "next_threshold": max(2.0, thr * 0.95),
    }
