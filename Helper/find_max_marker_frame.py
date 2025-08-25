# File: Helper/find_max_marker_frame.py
from __future__ import annotations
"""
Helper: find_max_marker_frame (angepasste Semantik)
---------------------------------------------------
Sucht den *ersten* Frame (aufsteigend), dessen Anzahl an Markern
< (marker_frame * 1.1) ist. Wird ein solcher Frame gefunden, kann der
aufrufende Zyklus beendet werden.

Rückgabe (dict):
- status: "FOUND" | "NONE" | "FAILED"
- frame: int (falls FOUND)
- count: int (Markeranzahl am gefundenen Frame)
- threshold: int (marker_frame * 1.1)
- reason: optional, bei Fehler
"""

from typing import Optional, Dict, Any
import bpy


def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def run_find_max_marker_frame(context: bpy.types.Context) -> Dict[str, Any]:
    clip = _get_active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no active MovieClip"}

    try:
        # Baseline: scene.marker_frame → Fallback: aktuelle Frameposition
        baseline = int(
            getattr(context.scene, "marker_frame", context.scene.frame_current)
            or context.scene.frame_current
        )
        threshold = int(baseline * 1.1)

        # Zähle Marker pro Frame über alle Tracks
        frame_counts: Dict[int, int] = {}

        # Hinweis: marker.frame ist ein int-ähnlicher Index im Clip
        for tr in clip.tracking.tracks:
            try:
                for m in tr.markers:
                    f = int(m.frame)
                    frame_counts[f] = frame_counts.get(f, 0) + 1
            except Exception:
                # Falls ein Track keine Marker-Liste o.ä. hat, einfach überspringen
                continue

        if not frame_counts:
            return {"status": "NONE", "threshold": threshold}

        # Ersten Frame (aufsteigend) finden, dessen Markeranzahl < threshold ist
        for f in sorted(frame_counts.keys()):
            c = frame_counts[f]
            if c < threshold:
                return {"status": "FOUND", "frame": f, "count": c, "threshold": threshold}

        # Nichts gefunden
        return {"status": "NONE", "threshold": threshold}

    except Exception as ex:
        return {"status": "FAILED", "reason": repr(ex)}
