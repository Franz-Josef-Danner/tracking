# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper: distanze (mit direkten Konsolen-Logs)

Aufgabe:
- Finde *neue* Marker (Tracks, die nach einem Pre-Snapshot erstellt wurden)
- Hole deren Marker am Ziel-Frame (selektierte, neu gesetzte Marker)
- Vergleiche deren Positionen mit *alten*, nicht gemuteten Markern am selben Frame
- Lösche neue Marker, die näher als `min_distance` an einem alten Marker liegen
- Selektiere alle übrig gebliebenen neuen Marker erneut

Logging:
- Gibt IMMER eine kompakte Zusammenfassung per `print()` aus
- Optional: detaillierte Zeilen (Positionen, nächster alter Marker, Distanz, Entscheidung) bis `debug_max_items`

Hinweis:
- Die Koordinaten liegen in normalisierten Clip-Koordinaten (`marker.co`).
"""
from __future__ import annotations

from typing import Iterable, Set, Tuple, List
import math
import bpy


LOG_PREFIX = "DISTANZE"


def _log(msg: str):
    print(f"{LOG_PREFIX}: {msg}")


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
    verbose: bool = True,
) -> dict:
    """Distanzbasierter Cleanup von NEUEN Markern am gegebenen Frame.

    Args:
        context: Blender-Context.
        pre_ptrs: Pointer-Snapshot der Tracks *vor* der Detection (64-bit ints).
        frame: Ziel-Frame (int).
        min_distance: Mindestabstand (normierte Clip-Koordinaten).
        select_remaining_new: Nach Cleanup alle verbliebenen neuen Marker erneut selektieren.
        debug_max_items: Anzahl Detailzeilen max.
        verbose: Wenn True, direkt in die Konsole loggen.

    Returns:
        Dict mit Status, Kennzahlen und einer Debug-Struktur.
    """
    clip = _resolve_clip(context)
    if not clip:
        if verbose:
            _log("NO_CLIP – kein MovieClip im Context gefunden.")
        return {"status": "NO_CLIP"}

    min_dist2 = float(min_distance) * float(min_distance)
    pre_ptrs_set: Set[int] = set(int(p) for p in (pre_ptrs or []))
    tracks = list(clip.tracking.tracks)

    if verbose:
        _log(
            f"Start frame={int(frame)} min_distance={float(min_distance):.6f} "
            f"tracks_total={len(tracks)} pre_ptrs={len(pre_ptrs_set)}"
        )

    # --- Alte Marker-Positionen sammeln ---
    old_positions: List[Tuple[float, float]] = []
    old_details = []
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
        if len(old_details) < debug_max_items:
            old_details.append((tr.name, pos))

    if verbose:
        _log(f"OLD markers at frame: count={len(old_positions)}")
        for name, pos in old_details:
            _log(f"  OLD '{name}': co=({pos[0]:.6f},{pos[1]:.6f})")

    # --- Neue Marker prüfen ---
    removed = 0
    kept = 0
    checked = 0
    skipped_unselected = 0

    new_details = []

    for tr in tracks:
        if int(tr.as_pointer()) in pre_ptrs_set:
            continue
        m = _get_marker_at_exact_frame(tr, frame)
        if not m:
            continue
        if not getattr(m, "select", False):
            skipped_unselected += 1
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
        dist = math.sqrt(min_d2) if min_d2 < float("inf") else None

        if len(new_details) < debug_max_items:
            new_details.append((tr.name, co_new, nearest_old, dist, too_close))

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

    # Detail-Logs
    if verbose:
        _log(
            f"NEW markers checked: {checked} (skipped_unselected={skipped_unselected})"
        )
        for name, co_new, nearest_old, dist, removed_flag in new_details:
            if nearest_old is not None and dist is not None:
                _log(
                    "  NEW '{name}': ({nx:.6f},{ny:.6f}) vs OLD ({ox:.6f},{oy:.6f}) -> "
                    "d={d:.6f} -> {decision}".format(
                        name=name,
                        nx=co_new[0], ny=co_new[1],
                        ox=nearest_old[0], oy=nearest_old[1],
                        d=dist,
                        decision=("REMOVE" if removed_flag else "KEEP"),
                    )
                )
            else:
                _log(
                    "  NEW '{name}': ({nx:.6f},{ny:.6f}) -> no OLD ref found".format(
                        name=name, nx=co_new[0], ny=co_new[1]
                    )
                )

    if verbose:
        _log(
            f"RESULT frame={int(frame)} removed={removed} kept={kept} "
            f"checked_new={checked} min_distance={float(min_distance):.6f}"
        )

    return {
        "status": "OK",
        "frame": int(frame),
        "checked_new": int(checked),
        "removed": int(removed),
        "kept": int(kept),
        "min_distance": float(min_distance),
        "debug": {
            "frame": int(frame),
            "min_distance": float(min_distance),
            "old_count": len(old_positions),
            "skipped_unselected": int(skipped_unselected),
            # Detaildaten verbleiben nur in Logs; Rückgabe hält kompakte Kennzahlen
        },
    }
