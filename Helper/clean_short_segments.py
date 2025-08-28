# Helper/clean_short_segments.py
# SPDX-License-Identifier: MIT
from __future__ import annotations
"""
Segmentweises Clean: Entfernt zu kurze Marker-Segmente innerhalb eines Tracks.

Definition:
- Ein Segment ist eine Folge von Markern mit konsekutiven Frames (dt == 1).
- Segmente, deren Länge (Anzahl Marker) < min_len ist, werden entfernt (Marker-DELETE).
- Muted Marker können optional als "Lücke" betrachtet werden (default: True).

Rückgabe (dict):
{
    "status": "OK",
    "tracks_visited": int,
    "segments_removed": int,
    "markers_removed": int,
    "tracks_emptied": int,   # wie viele Tracks dadurch leer wurden
}
"""

from typing import Dict, Any, List
import bpy

__all__ = ["clean_short_segments"]


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _get_active_clip(context) -> bpy.types.MovieClip | None:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _tracks_collection(clip) -> bpy.types.bpy_prop_collection | None:
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


def _iter_segments(
    markers: List[bpy.types.MovieTrackingMarker],
    *,
    treat_muted_as_gap: bool
) -> List[List[bpy.types.MovieTrackingMarker]]:
    """Zerlegt Marker in Segmente aus konsekutiven Frames (dt==1).
    Optional erzeugen 'mute'-Marker Lücken.
    """
    segs: List[List[bpy.types.MovieTrackingMarker]] = []
    if not markers:
        return segs

    # Sicherheit: nach Frame sortieren
    markers = sorted(markers, key=lambda m: int(getattr(m, "frame", 0)))

    curr: List[bpy.types.MovieTrackingMarker] = [markers[0]]
    for prev, curr_m in zip(markers, markers[1:]):
        f0 = int(getattr(prev, "frame", -10))
        f1 = int(getattr(curr_m, "frame", -10))
        dt = f1 - f0

        # Lücke, wenn Frames nicht konsekutiv oder (optional) wenn ein Marker gemutet ist
        gap = (dt != 1) or (
            treat_muted_as_gap and (getattr(prev, "mute", False) or getattr(curr_m, "mute", False))
        )

        if gap:
            segs.append(curr)
            curr = [curr_m]
        else:
            curr.append(curr_m)

    if curr:
        segs.append(curr)
    return segs


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def clean_short_segments(
    context: bpy.types.Context,
    *,
    min_len: int = 25,
    treat_muted_as_gap: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Entfernt Marker-Segmente mit Länge < min_len aus allen Tracks des aktiven Clips.
    Es werden ausschließlich Marker der betroffenen Segmente gelöscht (Tracks bleiben bestehen).

    Hinweis:
    - Wenn ein Track anschließend keine Marker mehr hat, bleibt er als leerer Track erhalten.
    """
    clip = _get_active_clip(context)
    if not clip:
        if verbose:
            print("[CleanShortSegments] No active MovieClip.")
        return {"status": "FAILED", "reason": "no active MovieClip"}

    tracks = _tracks_collection(clip) or []
    tracks_visited = 0
    segments_removed = 0
    markers_removed = 0
    tracks_emptied = 0

    # Optional: Depsgraph für UI-Konsistenz
    deps = context.evaluated_depsgraph_get() if hasattr(context, "evaluated_depsgraph_get") else None

    for tr in list(tracks):
        tracks_visited += 1
        # Snapshot der Marker (wichtig, da wir währenddessen löschen)
        markers = list(tr.markers)
        if not markers:
            continue

        segments = _iter_segments(markers, treat_muted_as_gap=treat_muted_as_gap)
        if verbose:
            lens = [len(s) for s in segments]
            print(f"[CleanShortSegments] Track='{tr.name}' segs={len(segments)} lens={lens[:10]}{'...' if len(lens) > 10 else ''}")

        # Zu kurze Segmente löschen
        for seg in segments:
            if len(seg) < int(min_len):
                # Marker DELETE: stabil über Frame löschen (robuster als remove(marker))
                for m in reversed(seg):
                    try:
                        f = int(getattr(m, "frame", -10))
                        tr.markers.delete_frame(f)
                        markers_removed += 1
                    except Exception as ex:
                        if verbose:
                            print(f"[CleanShortSegments] delete_frame failed @f{getattr(m,'frame', '?')}: {ex!r}")
                segments_removed += 1

        # Track leer geworden?
        try:
            if len(tr.markers) == 0:
                tracks_emptied += 1
        except Exception:
            pass

        # Depsgraph/UI aktualisieren
        if deps is not None:
            try:
                deps.update()
            except Exception:
                pass

    if verbose:
        print(
            f"[CleanShortSegments] tracks={tracks_visited} "
            f"seg_removed={segments_removed} markers_removed={markers_removed} "
            f"emptied={tracks_emptied}"
        )

    return {
        "status": "OK",
        "tracks_visited": tracks_visited,
        "segments_removed": segments_removed,
        "markers_removed": markers_removed,
        "tracks_emptied": tracks_emptied,
    }
