# SPDX-License-Identifier: MIT
from __future__ import annotations
"""
Segmentweises Clean: Entfernt nur zu kurze Marker-Segmente innerhalb eines Tracks.

Definition:
- Ein Segment ist eine Folge von Markern mit konsekutiven Frames (dt == 1).
- Segmente, deren Länge (Anzahl Marker) < min_len ist, werden entfernt.
- Muted Marker können optional als "Lücke" betrachtet werden (standardmäßig: ja).

Rückgabe (dict):
{
    "status": "OK",
    "tracks_visited": int,
    "segments_removed": int,
    "markers_removed": int,
    "tracks_emptied": int,   # wie viele Tracks durch das Entfernen leer wurden
}
"""

from typing import Dict, Any, List, Tuple
import bpy


__all__ = ["clean_short_segments"]


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


def _iter_segments(markers: List[bpy.types.MovieTrackingMarker], *, treat_muted_as_gap: bool) -> List[List[bpy.types.MovieTrackingMarker]]:
    """Zerlegt Marker in Segmente aus konsekutiven Frames (dt==1).
    Optional erzeugen 'mute'-Marker Lücken.
    """
    segs: List[List[bpy.types.MovieTrackingMarker]] = []
    if not markers:
        return segs

    # API ist i. d. R. sortiert, wir sichern das ab:
    markers = sorted(markers, key=lambda m: int(getattr(m, "frame", 0)))

    curr: List[bpy.types.MovieTrackingMarker]] = [markers[0]]
    for prev, curr_m in zip(markers, markers[1:]):
        f0 = int(getattr(prev, "frame", -10))
        f1 = int(getattr(curr_m, "frame", -10))
        dt = f1 - f0

        # Lücke durch nicht-konsekutive Frames oder durch mute (optional)
        gap = (dt != 1) or (treat_muted_as_gap and (getattr(prev, "mute", False) or getattr(curr_m, "mute", False)))

        if gap:
            # Segment abschließen
            segs.append(curr)
            curr = [curr_m]
        else:
            curr.append(curr_m)

    if curr:
        segs.append(curr)
    return segs


def clean_short_segments(
    context: bpy.types.Context,
    *,
    min_len: int = 25,
    treat_muted_as_gap: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Entfernt Marker-Segmente mit Länge < min_len aus allen Tracks des aktiven Clips.
    Löscht ausschließlich Marker der betroffenen Segmente (Tracks bleiben erhalten).

    Hinweise:
    - Wenn am Ende ein Track keine Marker mehr hat, bleibt er als leerer Track bestehen.
      (Das entspricht explizit dem Wunsch: KEIN vollständiges Track-Löschen.)
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

    for tr in list(tracks):
        tracks_visited += 1
        # Kopie der Marker-Liste (wichtig: beim Entfernen ändert sich die Collection)
        markers = list(tr.markers)
        if len(markers) == 0:
            continue

        # Segmente bestimmen
        segments = _iter_segments(markers, treat_muted_as_gap=treat_muted_as_gap)

        # Zu kurze Segmente löschen
        for seg in segments:
            if len(seg) < int(min_len):
                # Marker dieses Segments entfernen (von hinten nach vorne sicherer)
                for m in reversed(seg):
                    try:
                        tr.markers.remove(m)
                        markers_removed += 1
                    except Exception as ex:
                        if verbose:
                            print(f"[CleanShortSegments] remove failed: {ex!r}")
                segments_removed += 1

        # Statistik: leer geworden?
        if len(tr.markers) == 0:
            tracks_emptied += 1

    if verbose:
        print(f"[CleanShortSegments] tracks={tracks_visited} seg_removed={segments_removed} markers_removed={markers_removed} emptied={tracks_emptied}")

    return {
        "status": "OK",
        "tracks_visited": tracks_visited,
        "segments_removed": segments_removed,
        "markers_removed": markers_removed,
        "tracks_emptied": tracks_emptied,
    }
