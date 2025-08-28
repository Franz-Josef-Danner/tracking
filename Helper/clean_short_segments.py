# SPDX-License-Identifier: MIT
from __future__ import annotations
"""
Segmentweises Clean: Entfernt nur zu kurze Marker-Segmente innerhalb eines Tracks.

Definition:
- Ein Segment ist eine Folge von Markern mit konsekutiven Frames (dt == 1).
- Muted Marker können optional als "Lücke" gewertet werden (treat_muted_as_gap=True).
- Neu: Randschutz (Head/Tail) via skip_edge_segments=True. Alternativ separater
       Schwellenwert min_len_edge für Randsegmente.

Rückgabe (dict):
{
    "status": "OK",
    "tracks_visited": int,
    "segments_removed": int,
    "markers_removed": int,
    "tracks_emptied": int,   # wie viele Tracks durch das Entfernen leer wurden
}
"""

from typing import Dict, Any, List, Tuple, Optional
import bpy


__all__ = ["clean_short_segments"]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    """Finde aktiven MovieClip, bevorzugt CLIP_EDITOR; Fallback: erstes MovieClip."""
    try:
        space = getattr(context, "space_data", None)
        if getattr(space, "type", None) == "CLIP_EDITOR":
            clip = getattr(space, "clip", None)
            if clip:
                return clip
    except Exception:
        pass
    try:
        # weiterer Fallback über Kontext
        clip = getattr(context, "edit_movieclip", None)
        if clip:
            return clip
    except Exception:
        pass
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _markers_sorted(track: bpy.types.MovieTrackingTrack) -> List[bpy.types.MovieTrackingMarker]:
    try:
        # Marker per Frame aufsteigend, robuster Zugriff
        return sorted(list(track.markers), key=lambda m: int(getattr(m, "frame", 0)))
    except Exception:
        return list(track.markers)


def _segmentize_markers(
    markers: List[bpy.types.MovieTrackingMarker],
    *,
    treat_muted_as_gap: bool = True,
) -> List[List[bpy.types.MovieTrackingMarker]]:
    """Zerlegt Marker in Listen konsekutiver Segmente (dt==1)."""
    segs: List[List[bpy.types.MovieTrackingMarker]] = []
    if not markers:
        return segs

    curr: List[bpy.types.MovieTrackingMarker] = []
    prev_f: Optional[int] = None

    for m in markers:
        f = int(getattr(m, "frame", 0))
        if prev_f is None:
            curr = [m]
        else:
            dt = f - prev_f
            # Gap, wenn Frame-Sprung oder (optional) stumme Marker involviert
            if dt != 1 or (treat_muted_as_gap and (getattr(m, "mute", False) or getattr(curr[-1], "mute", False))):
                if curr:
                    segs.append(curr)
                curr = [m]
            else:
                curr.append(m)
        prev_f = f

    if curr:
        segs.append(curr)
    return segs


def _delete_markers(track: bpy.types.MovieTrackingTrack, markers_to_delete: List[bpy.types.MovieTrackingMarker]) -> int:
    """Löscht Marker sicher über rückwärtslaufende Indexliste."""
    if not markers_to_delete:
        return 0

    # Map: Marker -> Index (einmalig erzeugen)
    index_map = {}
    try:
        # Achtung: track.markers ist eine bpy_prop_collection; indices stabilisieren
        all_markers = list(track.markers)
        for idx, mk in enumerate(all_markers):
            index_map[id(mk)] = idx
    except Exception:
        # Fallback (langsamer): jedes Mal Index suchen
        all_markers = None

    deleted = 0
    # Indizes sammeln und rückwärts löschen
    if all_markers is not None:
        indices = [index_map.get(id(mk), None) for mk in markers_to_delete]
        indices = [i for i in indices if i is not None]
        for i in sorted(set(indices), reverse=True):
            try:
                track.markers.remove(track.markers[i])
                deleted += 1
            except Exception:
                pass
    else:
        # Fallback: lineares Suchen
        for mk in markers_to_delete:
            try:
                # Suche nach erstem identischen Objekt
                for i, existing in enumerate(track.markers):
                    if existing is mk:
                        track.markers.remove(track.markers[i])
                        deleted += 1
                        break
            except Exception:
                pass
    return deleted


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def clean_short_segments(
    context: bpy.types.Context = bpy.context,
    *,
    min_len: int = 5,
    treat_muted_as_gap: bool = True,
    skip_edge_segments: bool = True,
    min_len_edge: Optional[int] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Entfernt zu kurze Segmente (Marker-Folgen mit dt==1) innerhalb eines Tracks.

    Parameter:
    - min_len:        Mindestlänge für *interne* Segmente.
    - treat_muted_as_gap:  True → mute trennt Segmente (empf. für saubere Logik).
    - skip_edge_segments:  True → Head/Tail werden *nie* gelöscht (Default = Randschutz).
    - min_len_edge:   Optionaler separater Schwellwert für Head/Tail (nur wirksam, wenn
                      skip_edge_segments=False). Wenn None → Head/Tail nie löschen.

    Wirkung:
    - Nur Marker der betroffenen Segmente werden gelöscht, keine Track-Merge/Join-Operationen.
    - Leere Tracks werden nicht entfernt (werden jedoch gezählt und können anderweitig bereinigt werden).
    """
    clip = _get_active_clip(context)
    if not clip:
        if verbose:
            print("[CleanShortSeg] WARN: Kein aktiver MovieClip.")
        return {
            "status": "FAILED",
            "tracks_visited": 0,
            "segments_removed": 0,
            "markers_removed": 0,
            "tracks_emptied": 0,
        }

    tracks = list(clip.tracking.tracks)
    visited = 0
    seg_removed = 0
    mk_removed = 0
    emptied = 0

    for track in tracks:
        try:
            visited += 1
            markers = _markers_sorted(track)
            if not markers:
                continue

            segments = _segmentize_markers(markers, treat_muted_as_gap=treat_muted_as_gap)
            if not segments:
                continue

            # Kandidaten bestimmen
            to_delete: List[bpy.types.MovieTrackingMarker] = []
            n_seg = len(segments)

            for idx, seg in enumerate(segments):
                seg_len = len(seg)
                is_edge = (idx == 0) or (idx == n_seg - 1)

                if skip_edge_segments and is_edge:
                    # harter Rand-Schutz: nie löschen
                    continue

                # wenn Edge erlaubt, aber mit eigenem Schwellwert
                if (not skip_edge_segments) and is_edge:
                    if min_len_edge is None:
                        # Kein Edge-Threshold → Edge niemals löschen
                        continue
                    thr = int(min_len_edge)
                else:
                    thr = int(min_len)

                if seg_len < max(1, thr):
                    to_delete.extend(seg)

            if to_delete:
                before_cnt = len(track.markers)
                removed = _delete_markers(track, to_delete)
                mk_removed += removed
                if removed > 0:
                    seg_removed += 1  # zählt Segmente, die *mindestens* teilweise gelöscht wurden
                after_cnt = len(track.markers)
                if before_cnt > 0 and after_cnt == 0:
                    emptied += 1

        except Exception as ex:
            if verbose:
                name = getattr(track, "name", "<unnamed>")
                print(f"[CleanShortSeg] WARN: Track '{name}': {ex!s}")

    if verbose:
        edge_info = "ON (Head/Tail geschützt)" if skip_edge_segments else (
            f"OFF (Edge-threshold={min_len_edge})" if min_len_edge is not None else "OFF (Edge nie löschen)"
        )
        print(
            f"[CleanShortSeg] done | tracks={visited} | seg_removed={seg_removed} | "
            f"markers_removed={mk_removed} | emptied={emptied} | "
            f"min_len={min_len} | muted_as_gap={treat_muted_as_gap} | edge_guard={edge_info}"
        )

    return {
        "status": "OK",
        "tracks_visited": visited,
        "segments_removed": seg_removed,
        "markers_removed": mk_removed,
        "tracks_emptied": emptied,
    }
