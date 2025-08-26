from __future__ import annotations
"""
Helper: find_max_marker_frame (nach Szenenvariable, Szene-Zeitraum)
----------------------------------------------------------------------

Verwendet die Szenenvariable `scene.marker_frame` (vom UI gesetzt) und
bildet daraus die feste Schwelle `threshold = scene.marker_frame * 2`.

Es wird **ausschließlich innerhalb des Szenen-Zeitraums**
`scene.frame_start .. scene.frame_end` gesucht (aufsteigend). Sobald ein
Frame gefunden wird, bei dem die Anzahl **aktiver Marker** (pro Track
max. ein Marker, gemutete Tracks/Marker werden ignoriert) **< threshold**
ist, wird `FOUND` zurückgegeben. Existiert keiner → `NONE`.

Rückgabe (dict):

* status: "FOUND" | "NONE" | "FAILED"
* frame: int (falls FOUND)
* count: int (Markeranzahl am gefundenen Frame)
* threshold: int (scene.marker_frame * 2)
* reason: optional, bei Fehler
"""

from typing import Optional, Dict, Any
import bpy

__all__ = ["run_find_max_marker_frame"]


# ---------------------------------------------------------------------------
# Interna
# ---------------------------------------------------------------------------


def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    """Versucht, den aktiven MovieClip zu ermitteln.

    Bevorzugt den Clip des aktiven CLIP_EDITORs; Fallback: erstes
    vorhandenes MovieClip-Datenblock.
    """
    try:
        space = getattr(context, "space_data", None)
        if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
            return space.clip
    except Exception:
        pass

    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _get_tracks_collection(clip) -> Optional[bpy.types.bpy_prop_collection]:
    """Bevorzuge Tracks des aktiven Tracking-Objekts; Fallback: globale Tracks."""
    if not clip:
        return None
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
    """Zählt Marker an *frame* über alle Tracks.

    Regeln:
    - pro Track höchstens 1 Marker (früher Ausstieg via ``break``)
    - ignoriert gemutete Tracks und gemutete Marker
    """
    f = int(frame)
    count = 0
    for tr in tracks or []:
        try:
            if bool(getattr(tr, "mute", False)):
                continue
            for m in tr.markers:
                if int(getattr(m, "frame", -10 ** 9)) == f:
                    if not bool(getattr(m, "mute", False)):
                        count += 1
                    break  # pro Track nur einmal zählen
        except Exception:
            # Defensiv: Einzelne fehlerhafte Tracks/Masks ignorieren
            continue
    return count


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------


def run_find_max_marker_frame(context: bpy.types.Context) -> Dict[str, Any]:
    """Sucht den **ersten** Frame im Szenenbereich, dessen aktive Markerzahl
    **unter** der Schwelle ``threshold = scene.marker_frame * 2`` liegt.

    Die Prüfung erfolgt **für jeden Frame** im Bereich
    ``scene.frame_start .. scene.frame_end`` und respektiert damit den
    geforderten globalen Threshold-Vergleich (nicht nur für "weitergereichte"
    Kandidaten).
    """
    clip = _get_active_clip(context)
    if not clip:
        return {"status": "FAILED", "reason": "no active MovieClip"}

    try:
        scene = context.scene

        # Schwelle aus Szenenvariable marker_frame (UI-Wert)
        marker_frame_val = int(
            getattr(scene, "marker_frame", scene.frame_current) or scene.frame_current
        )
        threshold = int(marker_frame_val * 2)

        # Tracks ermitteln
        tracks = _get_tracks_collection(clip)
        if tracks is None:
            # Kein Tracking-Kontext vorhanden → keine Marker → keine Treffer
            return {"status": "NONE", "threshold": threshold}

        # --- Suche strikt im Szenenbereich ---
        s_start = int(getattr(scene, "frame_start", 1) or 1)
        s_end = int(getattr(scene, "frame_end", s_start) or s_start)
        if s_end < s_start:
            s_start, s_end = s_end, s_start

        # Ersten Frame im Szenenbereich finden, dessen Markeranzahl < threshold ist
        for f in range(s_start, s_end + 1):
            c = _count_active_markers_at_frame(tracks, f)
            if c < threshold:
                return {
                    "status": "FOUND",
                    "frame": int(f),
                    "count": int(c),
                    "threshold": int(threshold),
                }

        # Kein Frame unterschreitet die Schwelle
        return {"status": "NONE", "threshold": int(threshold)}

    except Exception as ex:  # Defensiver Catch um den Aufrufer nicht zu brechen
        return {"status": "FAILED", "reason": repr(ex)}
