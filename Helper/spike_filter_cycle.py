# Helper/spike_filter_cycle.py
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Optional, Dict, Any, List, Tuple
import bpy
import math

# Zwingend: segmentweises Cleanup (vom Nutzer gefordert)
try:
    from .clean_short_segments import clean_short_segments  # type: ignore
except Exception as _ex:
    clean_short_segments = None
    _CSS_IMPORT_ERR = _ex
else:
    _CSS_IMPORT_ERR = None

__all__ = ["run_marker_spike_filter_cycle"]


# ---------------------------------------------------------------------------
# Interna / Utilities
# ---------------------------------------------------------------------------

def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _get_tracks_collection(clip) -> Optional[bpy.types.bpy_prop_collection]:
    try:
        obj = clip.tracking.objects.active
        if obj and getattr(obj, "tracks", None):
            return obj.tracks
    except Exception:
        pass
    try:
        return clip.tracking.tracks
    except Exception:
        return None

def _to_pixel(vec01, size_xy) -> Tuple[float, float]:
    """Koordinate [0..1] → Pixel."""
    return float(vec01[0]) * float(size_xy[0]), float(vec01[1]) * float(size_xy[1])


def _collect_frame_velocities(
    clip: bpy.types.MovieClip,
) -> Dict[int, List[Tuple[bpy.types.MovieTrackingTrack,
                          bpy.types.MovieTrackingMarker,
                          bpy.types.MovieTrackingMarker,
                          Tuple[float, float]]]]:
    """
    Pro Ziel-Frame f1: Liste (track, prev_marker, curr_marker, v=(dx/dt, dy/dt)).
    - Gemutete Marker werden ignoriert.
    - Lücken (dt>1) sind erlaubt; Geschwindigkeit wird auf dt normiert.
    """
    result: Dict[int, List[Tuple[bpy.types.MovieTrackingTrack,
                                 bpy.types.MovieTrackingMarker,
                                 bpy.types.MovieTrackingMarker,
                                 Tuple[float, float]]]] = {}
    size = getattr(clip, "size", (1.0, 1.0))
    tracks = _get_tracks_collection(clip) or []

    for tr in tracks:
        markers: List[bpy.types.MovieTrackingMarker] = list(tr.markers)
        if len(markers) < 2:
            continue

        prev = markers[0]
        for i in range(1, len(markers)):
            curr = markers[i]

            # gemutete Marker nicht verwerten
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


def _apply_marker_outlier_filter(
    context: bpy.types.Context,
    *,
    threshold_px: float,
    action: str = "DELETE",
) -> int:
    """
    Marker-Filter pro Frame:
      - v_avg = Durchschnitt der Geschwindigkeiten
      - Kandidaten: Distanz zu v_avg > threshold_px
    action: "DELETE" (Default) | "MUTE" | "SELECT"
    Rückgabe: Anzahl betroffener Marker.
    """
    clip = _get_active_clip(context)
    if not clip:
        return 0

    frame_map = _collect_frame_velocities(clip)
    affected = 0

    act = action.upper().strip()
    do_delete = act == "DELETE"
    do_mute   = act == "MUTE"
    do_select = act == "SELECT"

    # Pro Frame erst Kandidaten sammeln, dann **in Reverse** löschen → stabile Indizes.
    for frame, entries in frame_map.items():
        if not entries:
            continue

        # v_avg
        sum_vx = 0.0
        sum_vy = 0.0
        for _, _, _, v in entries:
            sum_vx += v[0]
            sum_vy += v[1]
        inv_n = 1.0 / float(len(entries))
        v_avg = (sum_vx * inv_n, sum_vy * inv_n)

        # Kandidaten bestimmen
        to_handle: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingMarker, float]] = []
        for tr, m_prev, m_curr, v in entries:
            dvx = v[0] - v_avg[0]
            dvy = v[1] - v_avg[1]
            dev = math.hypot(dvx, dvy)
            if dev > threshold_px:
                to_handle.append((tr, m_curr, dev))

        if not to_handle:
            continue

        if do_delete:
            for tr, m_curr, dev in reversed(to_handle):
                try:
                    # Sicherer Pfad: über Frame löschen (robuster als remove(marker))
                    f = int(getattr(m_curr, "frame", -10))
                    tr.markers.delete_frame(f)
                    affected += 1
                except Exception as ex:
                    pass
        elif do_mute:
            for tr, m_curr, dev in to_handle:
                try:
                    m_curr.mute = True
                    affected += 1
                except Exception as ex:
                    pass
        elif do_select:
            for tr, m_curr, dev in to_handle:
                try:
                    m_curr.select = True
                    try:
                        tr.select = True
                    except Exception:
                        pass
                    affected += 1
                except Exception as ex:
                    pass

    return affected


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def run_marker_spike_filter_cycle(
    context: bpy.types.Context,
    *,
    track_threshold: float = 2.0,   # Pixel/Frame
    action: str = "DELETE",         # "DELETE" | "MUTE" | "SELECT"
    # Clean-Policy
    min_segment_len: Optional[int] = None,  # Default aus Scene
    treat_muted_as_gap: bool = True,
    run_segment_cleanup: bool = True,
) -> Dict[str, Any]:
    """
    Führt einen Marker-basierten Spike-Filter-Durchlauf aus (Pixel/Frame).
    - **Default-Aktion: DELETE** – Ausreißer-Marker werden hart entfernt.
    - Danach segmentweises Cleanup über `clean_short_segments(...)`.

    Scene-Defaults:
    - min_segment_len:  `scene.get('tco_min_seg_len', 25)` oder `scene.frames_track` (falls vorhanden)
    """
    if not _get_active_clip(context):
        return {"status": "FAILED", "reason": "no active MovieClip"}

    # **Untergrenze erzwingen**: auch wenn der Aufrufer < 2.0 übergibt
    thr = max(2.0, float(track_threshold))
    act = str(action or "DELETE").upper().strip()

    # 1) Marker-Filter
    affected = _apply_marker_outlier_filter(context, threshold_px=thr, action=act)
    key = "deleted" if act == "DELETE" else ("muted" if act == "MUTE" else "selected")

    # 2) Segment-Cleanup (optional via Flag)
    cleaned_segments = 0
    cleaned_markers = 0
    if not run_segment_cleanup:
        pass
    elif clean_short_segments is None:
        pass
    else:
        scene = getattr(context, "scene", None)
        if min_segment_len is None:
            # Priorität: tco_min_seg_len → frames_track → 25
            if scene is not None:
                try:
                    min_segment_len = int(scene.get("tco_min_seg_len", 0)) or int(getattr(scene, "frames_track", 0)) or 25
                except Exception:
                    min_segment_len = 25
            else:
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
        except Exception:
            pass

    return {
        "status": "OK",
        key: int(affected),
        "cleaned_segments": int(cleaned_segments),
        "cleaned_markers": int(cleaned_markers),
        "suggest_split_cleanup": True,  # Hinweis an den Coordinator
    }

