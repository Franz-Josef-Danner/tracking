# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper: distanze (Snapshot-basiert, unabhängig von Selektion)

Zweck laut Anforderung:
- **Alte Marker** = Tracks, die im Pre-Snapshot (`pre_ptrs`) enthalten sind → Hole deren Marker-Position am Ziel-Frame.
- **Neue Marker** = Tracks, die **nicht** im Snapshot waren → Hole deren Marker-Position am Ziel-Frame **auf die gleiche Weise**.
- Vergleiche Positionen (neu vs. alt) und lösche neue Marker, die näher als `min_distance` an einem alten liegen.
- Selektiere verbleibende neue Marker (Track + Marker) am Ende wieder.

Robustheit:
- **Frame-Flex**: Wenn am exakten Frame kein Marker existiert, nimm den *nächsten Key* innerhalb ±`frame_flex` Frames.
- **Mute-Regel**: Alte Marker werden nur berücksichtigt, wenn **nicht gemutet**. Für neue Marker gibt es keine Mute-Filterung (explizit nicht gefordert).
- **Keine Abhängigkeit von Selektion** (weder Track noch Marker) – beides wird nur am Ende gesetzt.

Logging (print):
- Start/Parameter-Zusammenfassung, Anzahl alter/neuer Kandidaten, Details pro geprüftem neuen Marker (Pos/Dist/Entscheidung), Abschluss-Zeile.

Koordinaten: `marker.co` in normalisierten Clip-Koordinaten [0..1].
"""
from __future__ import annotations

from typing import Iterable, Set, Tuple, List, Optional
import math
import bpy


LOG_PREFIX = "DISTANZE"


def _log(msg: str):
    print(f"{LOG_PREFIX}: {msg}")


def _resolve_clip(context: bpy.types.Context):
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip


def _get_marker_at_exact_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    try:
        m = track.markers.find_frame(frame, exact=True)
    except Exception:
        return None
    if not m or not hasattr(m, "co"):
        return None
    return m


def _get_marker_flexible(track: bpy.types.MovieTrackingTrack, frame: int, flex: int) -> tuple[Optional[bpy.types.MovieTrackingMarker], Optional[int]]:
    """Hole Marker am exakten Frame, sonst nächsten Key innerhalb ±flex.
    Rückgabe: (marker, marker_frame) – None/None wenn keiner existiert.
    """
    m = _get_marker_at_exact_frame(track, frame)
    if m:
        return m, frame
    if flex <= 0:
        return None, None
    best = None
    best_df = 10**9
    best_frame = None
    try:
        for mk in track.markers:
            f = int(getattr(mk, "frame", 10**9))
            df = abs(f - int(frame))
            if df <= flex and df < best_df:
                best = mk
                best_df = df
                best_frame = f
    except Exception:
        return None, None
    return (best, best_frame) if best is not None else (None, None)


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
    frame_flex: int = 2,
    select_remaining_new: bool = True,
    debug_max_items: int = 50,
    verbose: bool = True,
) -> dict:
    """Snapshot-basiertes Distanz-Cleanup am gegebenen Frame (±frame_flex).

    Es werden **alle** neuen Marker geprüft – völlig unabhängig von ihrer Selektion.
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
            f"tracks_total={len(tracks)} pre_ptrs={len(pre_ptrs_set)} frame_flex=±{int(frame_flex)}"
        )

    # --- Alte Marker sammeln (nicht gemutet) ---
    old_positions: List[Tuple[float, float]] = []
    old_details = []
    new_tracks: List[bpy.types.MovieTrackingTrack] = []

    for tr in tracks:
        if int(tr.as_pointer()) in pre_ptrs_set:
            m, mf = _get_marker_flexible(tr, frame, frame_flex)
            if m and not getattr(m, "mute", False):
                co = tuple(m.co)
                pos = (float(co[0]), float(co[1]))
                old_positions.append(pos)
                if len(old_details) < debug_max_items:
                    old_details.append((tr.name, pos, mf))
        else:
            new_tracks.append(tr)

    if verbose:
        _log(f"OLD markers at frame±{frame_flex}: count={len(old_positions)}")
        for name, pos, mf in old_details:
            _log(f"  OLD '{name}': co=({pos[0]:.6f},{pos[1]:.6f}) @f{mf}")
        _log(f"NEW tracks (by snapshot): total={len(new_tracks)}")

    # --- Neue Marker prüfen/entscheiden ---
    removed = 0
    kept = 0
    checked = 0
    skipped = 0  # neue Tracks ohne Marker innerhalb Flex

    new_details = []

    for tr in new_tracks:
        m, mf = _get_marker_flexible(tr, frame, frame_flex)
        if not m:
            skipped += 1
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
            if nearest_old is not None and dist is not None:
                new_details.append((tr.name, co_new, nearest_old, dist, too_close, mf))
            else:
                new_details.append((tr.name, co_new, None, None, too_close, mf))

        if too_close:
            try:
                tr.markers.delete_frame(mf if mf is not None else frame)
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

    # Logs
    if verbose:
        _log(f"NEW markers checked: {checked} (skipped_no_key_within_flex={skipped})")
        for name, co_new, nearest_old, dist, removed_flag, mf in new_details:
            if nearest_old is not None and dist is not None:
                _log(
                    "  NEW '{name}': ({nx:.6f},{ny:.6f}) @f{mf} vs OLD ({ox:.6f},{oy:.6f}) -> "
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
                    "  NEW '{name}': ({nx:.6f},{ny:.6f}) @f{mf} -> no OLD ref found -> {decision}".format(
                        name=name, nx=co_new[0], ny=co_new[1], mf=mf,
                        decision=("REMOVE" if removed_flag else "KEEP"),
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
            "new_total": len(new_tracks),
            "skipped_no_key_within_flex": int(skipped),
            "frame_flex": int(frame_flex),
        },
    }
