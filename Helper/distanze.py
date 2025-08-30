# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper: distanze

Aufgabe:
- Finde *neue* Marker (Tracks, die nach einem Pre-Snapshot erstellt wurden)
- Hole deren Marker am Ziel-Frame (selektierte, neu gesetzte Marker)
- Vergleiche deren Positionen mit *alten*, nicht gemuteten Markern am selben Frame
- Lösche neue Marker, die näher als `min_distance` an einem alten Marker liegen
- Selektiere alle übrig gebliebenen neuen Marker erneut

Hinweis:
- Die Koordinaten liegen in normalisierten Clip-Koordinaten (`marker.co`).
- Für den Pre-Snapshot wird eine Pointer-Menge (`pre_ptrs`) verwendet, wie sie der
  Coordinator vor der Detection aufnimmt.

API-Notizen (Blender):
- `bpy.types.MovieTrackingMarker.co -> Vector((x, y))`
- `track.markers.find_frame(frame, exact=True) -> MovieTrackingMarker | None`
- `track.markers.delete_frame(frame)`

Rückgabe (dict):
{
  'status': 'OK',
  'frame': int,
  'checked_new': int,         # Anzahl neuer Marker, die am Frame ausgewertet wurden
  'removed': int,             # Anzahl gelöschter Marker (zu nah an alt)
  'kept': int,                # Anzahl beibehaltene Marker
  'min_distance': float,
}
"""
from __future__ import annotations

from typing import Iterable, Set, Tuple, List
import math
import bpy


def _resolve_clip(context: bpy.types.Context):
    """Robuster Clip-Resolver analog zu tracking_coordinator."""
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip


def _get_marker_at_exact_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    """Sichere Abfrage des Markers am *exakten* Frame.
    Gibt `None` zurück, wenn es keinen exakten Marker gibt.
    """
    try:
        m = track.markers.find_frame(frame, exact=True)
    except Exception:
        return None
    # Manche Blender-Versionen liefern ggf. Dummy/geschätzte Marker –
    # defensiv prüfen, ob Koordinate vorhanden ist.
    if not m or not hasattr(m, "co"):
        return None
    return m


def _dist2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Quadratischer Abstand (vermeidet sqrt für Vergleiche)."""
    dx = (a[0] - b[0])
    dy = (a[1] - b[1])
    return dx * dx + dy * dy


def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Iterable[int] | Set[int],
    frame: int,
    min_distance: float = 0.01,  # Default wie im Coordinator-Kommentar
    select_remaining_new: bool = True,
) -> dict:
    """Distanzbasierter Cleanup von NEUEN Markern am gegebenen Frame.

    Args:
        context: Blender-Context.
        pre_ptrs: Pointer-Snapshot der Tracks *vor* der Detection (64-bit ints).
        frame: Ziel-Frame (int).
        min_distance: Mindestabstand (normierte Clip-Koordinaten) zwischen neuem und altem Marker.
        select_remaining_new: Nach Cleanup alle verbliebenen neuen Marker erneut selektieren.

    Returns:
        Dict mit Status und Kennzahlen (siehe Modul-Docstring).
    """
    clip = _resolve_clip(context)
    if not clip:
        return {"status": "NO_CLIP"}

    min_dist2 = float(min_distance) * float(min_distance)
    pre_ptrs_set: Set[int] = set(int(p) for p in pre_ptrs or [])

    tracks = list(clip.tracking.tracks)

    # --- Alte Marker-Positionen am Frame (nicht gemutet) sammeln ---
    old_positions: List[Tuple[float, float]] = []
    for tr in tracks:
        # Nur *alte* Tracks (Pointer bereits im Snapshot)
        if int(tr.as_pointer()) not in pre_ptrs_set:
            continue
        m = _get_marker_at_exact_frame(tr, frame)
        if not m:
            continue
        # Marker muss *nicht* gemutet sein
        if getattr(m, "mute", False):
            continue
        co = tuple(m.co)  # type: ignore[arg-type]
        old_positions.append((float(co[0]), float(co[1])))

    # Falls es keine alten Marker gibt, ist nichts zu löschen – nur (re-)selektieren
    if not old_positions:
        kept = 0
        for tr in tracks:
            if int(tr.as_pointer()) in pre_ptrs_set:
                continue  # alter Track
            m = _get_marker_at_exact_frame(tr, frame)
            if not m:
                continue
            # Nur neu gesetzte *selektierte* Marker als Kandidaten werten
            if not getattr(m, "select", False):
                continue
            if select_remaining_new:
                try:
                    m.select = True
                    tr.select = True
                except Exception:
                    pass
            kept += 1
        return {
            "status": "OK",
            "frame": int(frame),
            "checked_new": kept,
            "removed": 0,
            "kept": kept,
            "min_distance": float(min_distance),
        }

    # --- Neue Marker am Frame auswerten ---
    removed = 0
    kept = 0
    checked = 0
    for tr in tracks:
        # Nur *neue* Tracks (Pointer nicht im Snapshot)
        if int(tr.as_pointer()) in pre_ptrs_set:
            continue
        m = _get_marker_at_exact_frame(tr, frame)
        if not m:
            continue
        # Nur neu gesetzte *selektierte* Marker als Kandidaten
        if not getattr(m, "select", False):
            continue

        co_new = (float(m.co[0]), float(m.co[1]))
        checked += 1

        # Distanz zu *irgendeinem* alten Marker unter min_distance?
        too_close = False
        for co_old in old_positions:
            if _dist2(co_new, co_old) < min_dist2:
                too_close = True
                break

        if too_close:
            # Marker am Frame löschen
            try:
                tr.markers.delete_frame(frame)
                removed += 1
                continue
            except Exception:
                # Wenn Löschen fehlschlägt, behalten wir ihn (robuster Fallback)
                pass

        # Behalten & ggf. erneut selektieren
        if select_remaining_new:
            try:
                # Marker erneut selektieren (kann nach Operationen verloren gehen)
                m.select = True
                tr.select = True
            except Exception:
                pass
        kept += 1

    return {
        "status": "OK",
        "frame": int(frame),
        "checked_new": int(checked),
        "removed": int(removed),
        "kept": int(kept),
        "min_distance": float(min_distance),
    }
