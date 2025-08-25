# File: Helper/find_max_marker_frame.py
from __future__ import annotations
"""
Helper: find_max_marker_frame (angepasste Semantik)
---------------------------------------------------
Sucht den *ersten* Frame (aufsteigend), dessen Anzahl an Markern
< (baseline_marker_count * 1.5) ist. Die Baseline ist die Markeranzahl
am Szene-Frame `scene.marker_frame` (Fallback: `scene.frame_current`).

Wenn ein solcher Frame gefunden wird → status = "FOUND" (Zyklus kann enden).
Wenn keiner gefunden wird → status = "NONE" (Zyklus läuft weiter).

Rückgabe (dict):
- status: "FOUND" | "NONE" | "FAILED"
- frame: int (falls FOUND)
- count: int (Markeranzahl am gefundenen Frame)
- threshold: int (baseline_marker_count * 1.5, mindestens 1)
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


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def run_find_max_marker_frame(context: bpy.types.Context) -> Dict[str, Any]:
    clip = _get_active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no active MovieClip"}

    try:
        # Baseline-Frame: bevorzugt scene.marker_frame, sonst current
        baseline_frame = int(
            getattr(context.scene, "marker_frame", context.scene.frame_current)
            or context.scene.frame_current
        )

        tracks = _get_tracks_collection(clip)
        if tracks is None:
            return {"status": "NONE", "threshold": 1}

        # Marker pro Frame aggregieren
        frame_counts: Dict[int, int] = {}
        for tr in tracks:
            try:
                for m in tr.markers:
                    f = int(m.frame)
                    frame_counts[f] = frame_counts.get(f, 0) + 1
            except Exception:
                continue

        # Baseline-Markeranzahl ermitteln (0, falls keine Marker am Baseline-Frame)
        baseline_count = int(frame_counts.get(baseline_frame, 0))
        # Threshold mindestens 1, damit eine sinnvolle Suche möglich ist,
        # auch wenn baseline_count == 0 (dann gilt: count < 1 → Frames mit 0 Markern)
        threshold = max(1, baseline_count * 1.5)

        # Framebereich bestimmen (inkl. Frames mit 0 Markern berücksichtigen)
        start = int(getattr(clip, "frame_start", 1) or 1)
        dur = int(getattr(clip, "frame_duration", 0) or 0)
        if dur > 0:
            end = start + dur - 1
            search_iter = range(start, end + 1)
        else:
            # Fallback: nur bekannte Marker-Frames sortiert prüfen
            search_iter = sorted(frame_counts.keys())

        # Ersten Frame finden, dessen Markeranzahl < threshold ist
        for f in search_iter:
            c = int(frame_counts.get(int(f), 0))
            if c < threshold:
                return {"status": "FOUND", "frame": int(f), "count": c, "threshold": threshold}

        # Nichts gefunden
        return {"status": "NONE", "threshold": threshold}

    except Exception as ex:
        return {"status": "FAILED", "reason": repr(ex)}
