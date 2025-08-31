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

def _is_estimated(m: bpy.types.MovieTrackingMarker) -> bool:
    """Ein Marker gilt als 'estimated', wenn er NICHT keyframed ist.
    Primärsignal: not is_keyed. Fallback: vorhandenes 'is_estimate' Flag.
    """
    try:
        if hasattr(m, "is_keyed"):
            return not bool(getattr(m, "is_keyed"))
    except Exception:
        pass
    # Fallback – nur verwenden, wenn es existiert:
    if hasattr(m, "is_estimate"):
        try:
            return bool(getattr(m, "is_estimate"))
        except Exception:
            return False
    return False

# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def clean_short_segments(
    context: bpy.types.Context,
    *,
    min_len: int = 25,
    treat_muted_as_gap: bool = True,
    delete_estimated: bool = False,
    """
    Entfernt Marker-Segmente mit Länge < min_len aus allen Tracks des aktiven Clips.
    Es werden ausschließlich Marker der betroffenen Segmente gelöscht (Tracks bleiben bestehen).

    Hinweis:
    - Wenn ein Track anschließend keine Marker mehr hat, bleibt er als leerer Track erhalten.

    clip = _get_active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no active MovieClip"}

    tracks = _tracks_collection(clip) or []
    tracks_visited = 0
    segments_removed = 0
    markers_removed = 0
    tracks_emptied = 0
    estimated_removed = 0

    # Optional: Depsgraph für UI-Konsistenz
    deps = context.evaluated_depsgraph_get() if hasattr(context, "evaluated_depsgraph_get") else None

    for tr in list(tracks):
        tracks_visited += 1
        # Snapshot der Marker (wichtig, da wir währenddessen löschen)
        markers = list(tr.markers)
        if not markers:
            continue

        # 1) OPTION: Alle 'estimated' Marker unabhängig von Segmenten löschen
        if delete_estimated:
            deleted_any_est = False
            # rückwärts löschen → stabil
            for m in reversed(markers):
                try:
                    if _is_estimated(m):
                        f = int(getattr(m, "frame", -10))
                        tr.markers.delete_frame(f)
                        markers_removed += 1
                        estimated_removed += 1
                        deleted_any_est = True
                except Exception:
                    pass
            if deleted_any_est:
                # Marker-Snapshot nach Löschungen erneuern
                markers = list(tr.markers)
                if not markers:
                    # Track könnte leer geworden sein
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
                    # Nächster Track
                    continue


        # Set aller vorhandenen Frames des Tracks (für Save-Gate Prüfung)
        try:
            frames_in_track = {int(getattr(m, "frame", -10)) for m in markers}
        except Exception:
            frames_in_track = set()

        segments = _iter_segments(markers, treat_muted_as_gap=treat_muted_as_gap)

        # Zu kurze Segmente löschen
        for seg in segments:
            if len(seg) < int(min_len):
                # SAVE-GATE (1-Frame-Abstand):
                try:
                    first_f = int(getattr(seg[0], "frame", -10))
                    last_f  = int(getattr(seg[-1], "frame", -10))
                except Exception:
                    first_f = None
                    last_f = None

                to_delete = list(seg)

                # Head schützen, wenn (first_f - 1) existiert
                if first_f is not None and (first_f - 1) in frames_in_track:
                    if to_delete and to_delete[0] is seg[0]:
                        to_delete = to_delete[1:]

                # Tail schützen, wenn (last_f + 1) existiert
                if last_f is not None and (last_f + 1) in frames_in_track:
                    if to_delete and to_delete[-1] is seg[-1]:
                        to_delete = to_delete[:-1]

                deleted_any = False
                # Marker DELETE: stabil über Frame löschen (robuster als remove(marker))
                for m in reversed(to_delete):
                    try:
                        f = int(getattr(m, "frame", -10))
                        tr.markers.delete_frame(f)
                        markers_removed += 1
                        deleted_any = True
                    except Exception:
                        pass

                if deleted_any:
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

    return {
        "status": "OK",
        "tracks_visited": tracks_visited,
        "segments_removed": segments_removed,
        "markers_removed": markers_removed,
        "tracks_emptied": tracks_emptied,
        "estimated_removed": estimated_removed,

    }
