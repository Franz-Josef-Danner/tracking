from __future__ import annotations
"""
Custom Marker-Filter-Cycle (statt trackbasiertem `filter_tracks`)
-----------------------------------------------------------------

Dieses Modul führt genau einen Spike-Filter-Durchlauf aus:
- Marker mit zu großen Positionssprüngen werden `mute` gesetzt.
- Keine Verwendung von `bpy.ops.clip.filter_tracks`.
- Keine Löschung ganzer Tracks.
- Keine Finder- oder Clean-Logik.

Rückgabe (dict):
* status: "OK" | "FAILED"
* muted: Anzahl gemuteter Marker
* next_threshold: empfohlener neuer Schwellenwert
"""

from typing import Optional, Dict, Any
import bpy
import math

__all__ = ["run_marker_spike_filter_cycle"]


# ---------------------------------------------------------------------------
# Interna
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


def _distance(m1, m2) -> float:
    dx = m2.co[0] - m1.co[0]
    dy = m2.co[1] - m1.co[1]
    return math.hypot(dx, dy)


def _mute_spike_markers(context, threshold: float) -> int:
    """Geht alle Tracks durch und mutet Marker mit zu großen Sprüngen."""
    clip = _get_active_clip(context)
    if not clip:
        return 0

    tracks = _get_tracks_collection(clip)
    if not tracks:
        return 0

    muted = 0
    for track in tracks:
        markers = list(track.markers)
        for i in range(1, len(markers)):
            if markers[i - 1].mute or markers[i].mute:
                continue  # bereits gemutet

            d = _distance(markers[i - 1], markers[i])
            if d > threshold:
                markers[i].mute = True
                muted += 1
                print(f"[MarkerFilter] muted marker in '{track.name}' @ frame {markers[i].frame} (Δ={d:.4f})")

    return muted


def _lower_threshold(thr: float) -> float:
    next_thr = float(thr) * 0.95
    if abs(next_thr - float(thr)) < 1e-6 and thr > 0.0:
        next_thr = float(thr) - 1.0
    return max(0.0, next_thr)


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def run_marker_spike_filter_cycle(
    context: bpy.types.Context,
    *,
    track_threshold: float = 0.05,  # interpretiert als Marker-Sprung-Abstand
) -> Dict[str, Any]:
    """Führt einen Marker-basierten Spike-Filter-Durchlauf aus."""

    if not _get_active_clip(context):
        return {"status": "FAILED", "reason": "no active MovieClip"}

    muted = _mute_spike_markers(context, track_threshold)
    print(f"[MarkerFilter] muted {muted} marker(s)")

    next_thr = _lower_threshold(track_threshold)
    print(f"[MarkerFilter] next marker_threshold → {next_thr}")

    return {"status": "OK", "muted": int(muted), "next_threshold": float(next_thr)}
