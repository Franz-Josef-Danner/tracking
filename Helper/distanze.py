# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/distanze.py
Löscht neu gesetzte, selektierte Marker, die näher als ein Mindestabstand zu alten (nicht gemuteten)
Markern liegen – alles am selben Frame. Verbleibende neue Marker werden wieder selektiert.

Öffentliche API:
    run_distance_cleanup(context, *, pre_ptrs, frame, min_distance=0.01,
                         distance_unit="normalized", require_selected_new=True,
                         include_muted_old=False, select_remaining_new=True,
                         verbose=True) -> dict
"""

from __future__ import annotations
from typing import Iterable, Set, Dict, Any, Optional, Tuple
import bpy
from mathutils import Vector

__all__ = ("run_distance_cleanup",)

LOG_PREFIX = "DISTANZE"
def _log(msg: str, *, verbose: bool):
    if verbose:
        print(f"{LOG_PREFIX}: {msg}")

def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    scn = getattr(context, "scene", None)
    clip = getattr(context, "edit_movieclip", None)
    if clip:
        return clip
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == "CLIP_EDITOR":
        clip = getattr(space, "clip", None)
        if clip:
            return clip
    # Fallback Szene
    clip = getattr(scn, "clip", None) if scn else None
    if clip:
        return clip
    # Letzte Rettung: erster vorhandener Clip
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None

def _dist2(a: Vector, b: Vector, *, unit: str, clip_size: Optional[Tuple[float, float]]) -> float:
    if unit == "pixel" and clip_size:
        w, h = clip_size
        dx = (a.x - b.x) * w
        dy = (a.y - b.y) * h
        return dx * dx + dy * dy
    # normalized (0..1)
    dx = a.x - b.x
    dy = a.y - b.y
    return dx * dx + dy * dy

def cleanup_new_markers_at_frame(
    context: bpy.types.Context,
    *,
    pre_ptrs: Iterable[int] | Set[int],
    frame: int,
    min_distance: float = 0.01,
    distance_unit: str = "normalized",          # "normalized" | "pixel"
    require_selected_new: bool = True,          # nur neue Marker berücksichtigen, die selektiert sind
    include_muted_old: bool = False,            # gemutete alte Marker als Referenz zulassen
    select_remaining_new: bool = True,          # verbliebene neue Marker am Ende selektieren
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Kernlogik: siehe Modul-Docstring.
    """
    clip = _resolve_clip(context)
    if not clip:
        _log("NO_CLIP – kein MovieClip im Kontext gefunden.", verbose=verbose)
        return {"status": "FAILED", "reason": "no_clip"}

    # Größenkontext für Pixel-Abstände
    clip_size = None
    if distance_unit == "pixel":
        try:
            clip_size = (float(clip.size[0]), float(clip.size[1]))
        except Exception:
            # Fallback: keine Größe → weiche auf normalized aus
            distance_unit = "normalized"

    pre_ptrs_set: Set[int] = set(int(p) for p in (pre_ptrs or []))

    # --- Alte (Referenz-)Marker (nicht gemutet) am selben Frame sammeln ---
    old_positions: list[Vector] = []
    for tr in clip.tracking.tracks:
        if int(tr.as_pointer()) in pre_ptrs_set:
            try:
                m = tr.markers.find_frame(int(frame), exact=True)
            except TypeError:
                m = tr.markers.find_frame(int(frame))
            if not m:
                continue
            if not include_muted_old and getattr(m, "mute", False):
                continue
            co = getattr(m, "co", None)
            if co is None:
                continue
            old_positions.append(co.copy())

    # --- Neue Tracks bestimmen (nicht im Snapshot) ---
    new_tracks = [tr for tr in clip.tracking.tracks if int(tr.as_pointer()) not in pre_ptrs_set]

    _log(
        f"Start frame={int(frame)} min_distance={float(min_distance):.6f} unit={distance_unit} "
        f"tracks_total={len(list(clip.tracking.tracks))} pre_ptrs={len(pre_ptrs_set)} old={len(old_positions)} "
        f"new_tracks={len(new_tracks)}",
        verbose=verbose,
    )

    min_d2 = float(min_distance) * float(min_distance)
    removed = 0
    kept = 0
    checked = 0
    skipped_no_marker = 0
    skipped_unselected = 0

    # --- Für jeden neuen Track den Marker am exakt selben Frame prüfen ---
    for tr in new_tracks:
        try:
            m = tr.markers.find_frame(int(frame), exact=True)
        except TypeError:
            m = tr.markers.find_frame(int(frame))
        if not m:
            skipped_no_marker += 1
            continue

        # nur selektierte neue Marker berücksichtigen (wie gefordert)
        if require_selected_new and not (getattr(m, "select", False) or getattr(tr, "select", False)):
            skipped_unselected += 1
            continue

        pos = getattr(m, "co", None)
        if pos is None:
            skipped_no_marker += 1
            continue

        checked += 1

        # Abstand zum nächsten alten Marker bestimmen
        nearest_d2 = float("inf")
        for old_pos in old_positions:
            d2 = _dist2(pos, old_pos, unit=distance_unit, clip_size=clip_size)
            if d2 < nearest_d2:
                nearest_d2 = d2

        too_close = nearest_d2 < min_d2 if old_positions else False

        if too_close:
            # neuen Marker am Frame löschen
            try:
                tr.markers.delete_frame(int(frame))
                removed += 1
                _log(f"  NEW '{tr.name}': DELETE (too_close; d2={nearest_d2:.6f} < min_d2={min_d2:.6f})", verbose=verbose)
                continue
            except Exception as ex:
                _log(f"  NEW '{tr.name}': delete_frame() FAILED → {ex}", verbose=verbose)
                # Wenn das Löschen scheitert, selektieren wir ihn NICHT
                continue

        # behalten → optional selektieren
        if select_remaining_new:
            try:
                m.select = True
                tr.select = True
            except Exception:
                pass
        kept += 1
        _log(f"  NEW '{tr.name}': KEEP", verbose=verbose)

    _log(
        f"RESULT frame={int(frame)} removed={removed} kept={kept} "
        f"checked_new={checked} skipped_no_marker={skipped_no_marker} skipped_unselected={skipped_unselected} "
        f"min_distance={float(min_distance):.6f} unit={distance_unit}",
        verbose=verbose,
    )

    return {
        "status": "OK",
        "frame": int(frame),
        "removed": int(removed),
        "kept": int(kept),
        "checked_new": int(checked),
        "skipped_no_marker": int(skipped_no_marker),
        "skipped_unselected": int(skipped_unselected),
        "min_distance": float(min_distance),
        "distance_unit": distance_unit,
        "old_count": len(old_positions),
        "new_total": len(new_tracks),
    }

# Öffentliche Thin-Wrapper-API (kompatibel zum Operator-Import)
def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Iterable[int] | Set[int],
    frame: int,
    min_distance: float = 0.01,
    distance_unit: str = "normalized",          # "normalized" | "pixel"
    require_selected_new: bool = True,
    include_muted_old: bool = False,
    select_remaining_new: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Öffentliche API – delegiert an cleanup_new_markers_at_frame().
    """
    return cleanup_new_markers_at_frame(
        context,
        pre_ptrs=pre_ptrs,
        frame=frame,
        min_distance=min_distance,
        distance_unit=distance_unit,
        require_selected_new=require_selected_new,
        include_muted_old=include_muted_old,
        select_remaining_new=select_remaining_new,
        verbose=verbose,
    )
