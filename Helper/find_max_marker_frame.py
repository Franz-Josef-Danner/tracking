# File: Helper/find_max_marker_frame.py
from __future__ import annotations
"""
Helper: find_max_marker_frame (nach Szenenvariable, Szene-Zeitraum)
------------------------------------------------------------------
Verwendet die Szenenvariable `scene.marker_frame` (vom UI gesetzt) und
bildet daraus die feste Schwelle `threshold = scene.marker_frame * 2`.

Es wird **ausschließlich innerhalb des Szenen-Zeitraums**
`scene.frame_start .. scene.frame_end` gesucht (aufsteigend). Sobald ein
Frame gefunden wird, bei dem die Anzahl **aktiver Marker** (pro Track
max. ein Marker, gemutete Tracks/Marker werden ignoriert) **< threshold**
ist, wird `FOUND` zurückgegeben. Existiert keiner → `NONE`.

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
    - pro Track höchstens 1 Marker (früher Ausstieg via break)
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
        scene = context.scene

        # Schwelle aus Szenenvariable marker_frame (UI-Wert)
        marker_frame_val = int(getattr(scene, "marker_frame", scene.frame_current) or scene.frame_current)
        threshold = int(marker_frame_val * 2)

        tracks = _get_tracks_collection(clip)
        if tracks is None:
            return {"status": "NONE", "threshold": threshold}

        # --- Suche strikt im Szenenbereich ---
        s_start = int(getattr(scene, "frame_start", 1) or 1)
        s_end = int(getattr(scene, "frame_end", s_start) or s_start)
        if s_end < s_start:
            s_start, s_end = s_end, s_start

        # Ersten Frame im Szenenbereich finden, dessen Markeranzahl < threshold ist
        for f in range(s_start, s_end + 1):
            c = _count_active_markers_at_frame(tracks, int(f))
            if c < threshold:
                return {"status": "FOUND", "frame": int(f), "count": int(c), "threshold": int(threshold)}

        return {"status": "NONE", "threshold": int(threshold)}

    except Exception as ex:
        return {"status": "FAILED", "reason": repr(ex)}
