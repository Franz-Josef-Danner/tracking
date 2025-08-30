# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper: distanze (mit Debug-Logs)

Aufgabe:
- Finde *neue* Marker (Tracks, die nach einem Pre-Snapshot erstellt wurden)
- Hole deren Marker am Ziel-Frame (selektierte, neu gesetzte Marker)
- Vergleiche deren Positionen mit *alten*, nicht gemuteten Markern am selben Frame
- Lösche neue Marker, die näher als `min_distance` an einem alten Marker liegen
- Selektiere alle übrig gebliebenen neuen Marker erneut

Debug-Ausgabe:
- Gibt die Anzahl alter Marker, neue geprüfte Marker und übersprungene Marker aus
- Listet Detailinfos (Positionen, nächster alter Marker, Distanz, Entscheidung) für max. N Marker

Hinweis:
- Die Koordinaten liegen in normalisierten Clip-Koordinaten (`marker.co`).
"""
from __future__ import annotations

from typing import Iterable, Set, Tuple, List, Dict, Any
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
    min_distance: float = 0.01,
    select_remaining_new: bool = True,
    debug_max_items: int = 50,
) -> dict:
    """Distanzbasierter Cleanup von NEUEN Markern am gegebenen Frame.

    Args:
        context: Blender-Context.
        pre_ptrs: Pointer-Snapshot der Tracks *vor* der Detection (64-bit ints).
        frame: Ziel-Frame (int).
        min_distance: Mindestabstand (normierte Clip-Koordinaten).
        select_remaining_new: Nach Cleanup alle verbliebenen neuen Marker erneut selektieren.
        debug_max_items: Wie viele Detail-Einträge maximal zurückgegeben werden.

    Returns:
        Dict mit Status, Kennzahlen und Debug-Daten.
    """
    clip = _resolve_clip(context)
    if not clip:
        return {"status": "NO_CLIP"}

    min_dist2 = float(min_distance) * float(min_distance)
    pre_ptrs_set: Set[int] = set(int(p) for p in pre_ptrs or [])

    tracks = list(clip.tracking.tracks)

    debug: Dict[str, Any] = {
        "frame": int(frame),
        "min_distance": float(min_distance),
        "old": [],
        "old_count": 0,
        "new_checked": [],
        "skipped_unselected": 0,
    }

    # --- Alte Marker-Positionen sammeln ---
    old_positions: List[Tuple[float, float]] = []
    for tr in tracks:
        if int(tr.as_pointer()) not in pre_ptrs_set:
            continue
        m = _get_marker_at_exact_frame(tr, frame)
        if not m:
            continue
        if getattr(m, "mute", False):
            continue
        co = tuple(m.co)
        pos = (float(co[0]), float(co[1]))
        old_positions.append(pos)
        if len(debug["old"]) < debug_max_items:
            debug["old"].append({"track": tr.name, "co": pos})
    debug["old_count"] = len(old_positions)

    removed = 0
    kept = 0
    checked = 0

    for tr in tracks:
        if int(tr.as_pointer()) in pre_ptrs_set:
            continue
        m = _get_marker_at_exact_frame(tr, frame)
        if not m:
            continue
        if not getattr(m, "select", False):
            debug["skipped_unselected"] += 1
            continue

        co_new = (float(m.co[0]), float(m.co[1]))
        checked += 1

        nearest_old = None
        min_d2 = float("inf")
        for co_old in old_positions:
            d2 = _dist2(co_new, co_old)
            if d2 < min_d2:
                min_d2 = d2
                nearest_old = co_old

        too_close = (min_d2 < min_dist2)

        if len(debug["new_checked"]) < debug_max_items:
            debug["new_checked"].append({
                "track": tr.name,
                "co_new": co_new,
                "nearest_old": tuple(nearest_old) if nearest_old else None,
                "dist": math.sqrt(min_d2) if min_d2 < float("inf") else None,
                "removed": bool(too_close),
            })

        if too_close:
            try:
                tr.markers.delete_frame(frame)
                removed += 1
                continue
            except Exception:
                pass

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
        "checked_new": int(checked),
        "removed": int(removed),
        "kept": int(kept),
        "min_distance": float(min_distance),
        "debug": debug,
    }
