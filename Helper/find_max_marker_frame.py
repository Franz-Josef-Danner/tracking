# File: Helper/find_max_marker_frame.py
from __future__ import annotations
"""
Helper: find_max_marker_frame (nach Szenenvariable)
---------------------------------------------------
Verwendet die Szenenvariable `scene.marker_frame` (vom UI gesetzt) und
bildet daraus die feste Schwelle `threshold = scene.marker_frame * 2`.

Dann wird der Clip zeitlich (aufsteigend) durchsucht. Sobald ein Frame
gefunden wird, bei dem die Anzahl **aktiver Marker** (Marker existiert an
Frame f, Track und Marker nicht gemutet) **< threshold** ist, wird
`FOUND` zurückgegeben. Wenn kein solcher Frame existiert: `NONE`.

Rückgabe (dict):
- status: "FOUND" | "NONE" | "FAILED"
- frame: int (falls FOUND)
- count: int (Markeranzahl am gefundenen Frame)
- threshold: int (scene.marker_frame * 2)
- reason: optional, bei Fehler
"""

from typing import Optional, Dict, Any
import bpy


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
    """Bevorzuge Tracks des aktiven Tracking-Objekts; Fallback: globale Tracks."""
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


def _count_active_markers_at_frame(tracks, frame: int) -> int:
    """Zählt Marker an `frame` über alle Tracks.
    - zählt pro Track höchstens 1 Marker (typischerweise gibt es pro Frame max. einen Marker je Track)
    - ignoriert gemutete Tracks/Marker
    """
    f = int(frame)
    count = 0
    for tr in tracks:
        try:
            if bool(getattr(tr, "mute", False)):
                continue
            for m in tr.markers:
                if int(getattr(m, "frame", -10**9)) == f:
                    if not bool(getattr(m, "mute", False)):
                        count += 1
                    break  # pro Track nur einmal zählen
        except Exception:
            continue
    return count


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def run_find_max_marker_frame(context: bpy.types.Context) -> Dict[str, Any]:
    clip = _get_active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no active MovieClip"}

    try:
        # Schwelle aus Szenenvariable marker_frame (UI-Wert)
        scene = context.scene
        marker_frame_val = int(getattr(scene, "marker_frame", scene.frame_current) or scene.frame_current)
        threshold = int(marker_frame_val * 2)

        tracks = _get_tracks_collection(clip)
        if tracks is None:
            return {"status": "NONE", "threshold": threshold}

        # Framebereich bestimmen (Clip-Start bis -Ende)
        start = int(getattr(clip, "frame_start", 1) or 1)
        dur = int(getattr(clip, "frame_duration", 0) or 0)
        if dur > 0:
            end = start + dur - 1
            search_iter = range(start, end + 1)
        else:
            # Fallback: bekannte Marker-Frames sortiert prüfen
            frames = set()
            for tr in tracks:
                try:
                    frames.update(int(m.frame) for m in tr.markers)
                except Exception:
                    pass
            if not frames:
                return {"status": "NONE", "threshold": threshold}
            search_iter = sorted(frames)

        # Suche: erster Frame mit count < threshold
        for f in search_iter:
            c = _count_active_markers_at_frame(tracks, int(f))
            if c < threshold:
                return {"status": "FOUND", "frame": int(f), "count": int(c), "threshold": int(threshold)}

        return {"status": "NONE", "threshold": int(threshold)}

    except Exception as ex:
        return {"status": "FAILED", "reason": repr(ex)}
