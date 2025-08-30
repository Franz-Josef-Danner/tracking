# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper: distanze (Snapshot-basiert, optional Pixel- oder Normalized-Distanz)

Zweck:
- **Alte Marker** = Tracks im Pre-Snapshot (`pre_ptrs`) → Marker-Position am Ziel-Frame ermitteln.
- **Neue Marker** = Tracks *nicht* im Snapshot → Marker-Position am Ziel-Frame *gleich* ermitteln.
- Abstand neu vs. alt vergleichen und neue Marker löschen, wenn Distanz < `min_distance`.
- Verbleibende neue Marker am Ende wieder selektieren.

Robustheit:
- **Frame-Flex** (`frame_flex`): Falls am exakten Frame kein Key existiert, wird der nächste Key innerhalb ±N Frames verwendet
  (für *alte* und *neue* Marker).
- **Mute-Regel**: Alte Marker nur berücksichtigen, wenn *nicht gemutet*.
- **Unabhängig von Selektion**: Selektion wird erst am Ende gesetzt.

Einheiten:
- `distance_unit="normalized"` → Vergleich in Clip-Normalized-Koordinaten (0..1).
- `distance_unit="pixel"`      → Vergleich in Pixeln (unter Nutzung von `clip.size`).

Logging:
- Ausführliche print-Logs (Start, Kandidaten, Detailvergleiche, Resultat).
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


def _get_marker_flexible(
    track: bpy.types.MovieTrackingTrack, frame: int, flex: int
) -> tuple[Optional[bpy.types.MovieTrackingMarker], Optional[int]]:
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


def _dist2_units(
    a: Tuple[float, float],
    b: Tuple[float, float],
    *,
    unit: str,
    clip: Optional[bpy.types.MovieClip],
) -> float:
    """Quadratischer Abstand in gewünschter Einheit."""
    if unit == "pixel" and clip is not None:
        try:
            W, H = float(clip.size[0]), float(clip.size[1])
        except Exception:
            # Fallback: falls clip.size nicht verfügbar, normalisiert vergleichen
            W, H = 1.0, 1.0
        dx = (a[0] - b[0]) * W
        dy = (a[1] - b[1]) * H
        return dx * dx + dy * dy
    # normalized
    dx = (a[0] - b[0])
    dy = (a[1] - b[1])
    return dx * dx + dy * dy


def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Iterable[int] | Set[int],
    frame: int,
    min_distance: float = 200,
    frame_flex: int = 2,
    select_remaining_new: bool = True,
    debug_max_items: int = 50,
    verbose: bool = True,
    distance_unit: str = "normalized",  # "normalized" | "pixel"
) -> dict:
    """Snapshot-basiertes Distanz-Cleanup am gegebenen Frame (±frame_flex).

    Es werden **alle** neuen Marker geprüft – völlig unabhängig von ihrer Selektion.
    `min_distance` ist abhängig von `distance_unit`:
      - "normalized": Einheiten in Clip-Normalized-Koordinaten (0..1)
      - "pixel":      Einheiten in Pixeln (unter Nutzung von clip.size)
    """
    clip = _resolve_clip(context)
    if not clip:
        if verbose:
            _log("NO_CLIP – kein MovieClip im Context gefunden.")
        return {"status": "NO_CLIP"}

    # Schwellenwert^2 in der gewählten Einheit (px² oder norm²)
    min_dist2 = float(min_distance) * float(min_distance)

    pre_ptrs_set: Set[int] = set(int(p) for p in (pre_ptrs or []))
    tracks = list(clip.tracking.tracks)

    if verbose:
        try:
            W, H = (int(clip.size[0]), int(clip.size[1]))
            wh_info = f"{W}x{H}px"
        except Exception:
            wh_info = "unknown size"
        _log(
            f"Start frame={int(frame)} min_distance={float(min_distance):.6f} "
            f"unit={distance_unit} clip={wh_info} "
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
            d2 = _dist2_units(co_new, co_old, unit=distance_unit, clip=clip)
            if d2 < min_d2:
                min_d2 = d2
                nearest_old = co_old

        too_close = (min_d2 < min_dist2)
        # Für die lesbare Log-Distanz (nicht-quadratisch):
        if nearest_old is not None:
            d_disp = math.sqrt(
                _dist2_units(co_new, nearest_old, unit=distance_unit, clip=clip)
            )
        else:
            d_disp = None

        if len(new_details) < debug_max_items:
            new_details.append((tr.name, co_new, nearest_old, d_disp, too_close, mf))

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
                    "d={d:.3f} {unit} -> {decision}".format(
                        name=name,
                        nx=co_new[0],
                        ny=co_new[1],
                        ox=nearest_old[0],
                        oy=nearest_old[1],
                        d=dist,
                        unit=("px" if distance_unit == "pixel" else "norm"),
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
            f"checked_new={checked} min_distance={float(min_distance):.6f} unit={distance_unit}"
        )

    return {
        "status": "OK",
        "frame": int(frame),
        "checked_new": int(checked),
        "removed": int(removed),
        "kept": int(kept),
        "min_distance": float(min_distance),
        "distance_unit": distance_unit,
        "debug": {
            "frame": int(frame),
            "min_distance": float(min_distance),
            "distance_unit": distance_unit,
            "old_count": len(old_positions),
            "new_total": len(new_tracks),
            "skipped_no_key_within_flex": int(skipped),
            "frame_flex": int(frame_flex),
        },
    }
