# File: Helper/find_max_marker_frame.py
from __future__ import annotations
"""
Helper: find_max_marker_frame
-----------------------------
Sucht nach einem Frame, der >= marker_frame * 2 liegt.

Rückgabe (dict):
- status: "FOUND" | "NONE" | "FAILED"
- frame: int (falls FOUND)
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
        # Basiswert marker_frame oder Fallback auf aktuelle Frameposition
        baseline = int(
            getattr(context.scene, "marker_frame", context.scene.frame_current)
            or context.scene.frame_current
        )
        target = baseline * 2

        best_frame: Optional[int] = None

        # Alle Marker durchlaufen
        for tr in clip.tracking.tracks:
            for marker in tr.markers:
                f = int(marker.frame)
                if f >= target:
                    if best_frame is None or f < best_frame:
                        best_frame = f

        if best_frame is not None:
            return {"status": "FOUND", "frame": best_frame}

        return {"status": "NONE"}

    except Exception as ex:
        return {"status": "FAILED", "reason": repr(ex)}


# Selftest
if __name__ == "__main__":
    print("[find_max_marker_frame] Modul geladen (kein automatischer Test)")
