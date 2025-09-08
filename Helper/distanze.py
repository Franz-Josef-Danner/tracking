# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/distanze.py

Überarbeitetes Distanz-Cleanup mit optionaler Selbsterkennung der Alt-/Neu-Mengen.
"""

from __future__ import annotations
import bpy
from math import isfinite
from typing import Iterable, Set, Dict, Any, Optional, Tuple

# bestehende Imports/Utilities bleiben unverändert …

__all__ = ("run_distance_cleanup",)


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen für Selbsterkennung (neu)
# ---------------------------------------------------------------------------
def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    scn = getattr(context, "scene", None)
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        space = getattr(context, "space_data", None)
        if space and getattr(space, "type", None) == "CLIP_EDITOR":
            clip = getattr(space, "clip", None)
    if not clip and scn:
        clip = getattr(scn, "clip", None)
    if not clip:
        try:
            clip = next(iter(bpy.data.movieclips))
        except Exception:
            clip = None
    return clip


def _track_marker_at_frame(
    tr: bpy.types.MovieTrackingTrack, frame: int
) -> Tuple[bool, Optional[bpy.types.MovieTrackingMarker]]:
    try:
        try:
            m = tr.markers.find_frame(int(frame), exact=True)
        except TypeError:
            m = tr.markers.find_frame(int(frame))
        return (m is not None), m
    except Exception:
        return (False, None)


def _collect_old_new_sets(
    context: bpy.types.Context,
    frame: int,
    *,
    require_selected_new: bool,
    include_muted_old: bool,
) -> Tuple[Set[int], Set[int], int, int]:
    """
    Liefert:
      - old_set: Pointer alter Tracks (alle Marker @frame, ggf. gemutete ausgeschlossen)
      - new_set: Pointer neuer Tracks:
          * Wenn require_selected_new=True: Tracks, die @frame selektiert sind
            (Track- oder Marker-Selektion genügt)
          * Sonst: Tracks mit Marker @frame, die nicht gemutet sind
      - old_count_markers: Anzahl Referenzmarker @frame (ohne gemutete, wenn include_muted_old=False)
      - new_count_markers: Anzahl Marker @frame in new_set (für Log)
    """
    clip = _resolve_clip(context)
    if not clip:
        return set(), set(), 0, 0

    old_set: Set[int] = set()
    new_set: Set[int] = set()
    old_cnt = 0
    new_cnt = 0
    for tr in getattr(clip.tracking, "tracks", []):
        ok, m = _track_marker_at_frame(tr, frame)
        if not ok or not m:
            continue
        if not include_muted_old and (getattr(m, "mute", False) or getattr(tr, "mute", False)):
            continue

        ptr = int(tr.as_pointer())
        old_set.add(ptr)
        old_cnt += 1

        # Neu-Kriterium
        if require_selected_new:
            is_sel = bool(getattr(tr, "select", False)) or bool(getattr(m, "select", False))
            if is_sel:
                new_set.add(ptr)
                new_cnt += 1
        else:
            # „Neu“ = nicht gemutet am Frame
            if not (getattr(m, "mute", False) or getattr(tr, "mute", False)):
                new_set.add(ptr)
                new_cnt += 1

    # Wichtig: „neu“ darf nicht gleichzeitig „alt“ sein, sonst ist die Differenz leer.
    old_set = old_set.difference(new_set)
    return old_set, new_set, old_cnt, new_cnt


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    pre_ptrs: Optional[Set[int]] = None,
    frame: int,
    min_distance: Optional[float] = 200,
    distance_unit: str = "pixel",
    require_selected_new: bool = True,
    include_muted_old: bool = False,
    select_remaining_new: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Wenn pre_ptrs is None:
      - ermittelt die Funktion intern die Referenz- („alt“) und Kandidaten- („neu“) Sets
        basierend auf Selektion @frame und Muting-Flags.
    Andernfalls:
      - verhält sich wie bisher (pre_ptrs = alte Tracks; neu = alle @frame, die nicht in pre_ptrs sind).
    """
    log = print if verbose else (lambda *a, **k: None)
    clip = _resolve_clip(context)
    if not clip:
        return {"status": "NO_CLIP", "frame": frame}

    # Alt/Neu bestimmen
    if pre_ptrs is None:
        old_set, new_set, old_cnt_m, new_cnt_m = _collect_old_new_sets(
            context,
            frame,
            require_selected_new=require_selected_new,
            include_muted_old=include_muted_old,
        )
    else:
        # „klassischer“ Pfad: pre_ptrs = alt; neu = alle @frame, die nicht in pre_ptrs sind
        old_set, new_set, old_cnt_m, new_cnt_m = set(pre_ptrs), set(), 0, 0
        for tr in clip.tracking.tracks:
            ok, m = _track_marker_at_frame(tr, frame)
            if not ok or not m:
                continue
            if not include_muted_old and (getattr(m, "mute", False) or getattr(tr, "mute", False)):
                continue
            ptr = int(tr.as_pointer())
            if ptr in old_set:
                old_cnt_m += 1
            else:
                if (not require_selected_new) or bool(getattr(tr, "select", False) or getattr(m, "select", False)):
                    new_set.add(ptr)
                    new_cnt_m += 1

    log(
        f"[DISTANZE] run_distance_cleanup called: frame={frame}, min_distance={min_distance}, unit={distance_unit}, "
        f"require_selected_new={require_selected_new}, include_muted_old={include_muted_old}, "
        f"select_remaining_new={select_remaining_new}"
    )

    log(
        f"[DISTANZE] Starting cleanup on frame {frame} with min_distance={min_distance} {distance_unit}; old tracks={len(old_set)}"
    )
    log(
        f"[DISTANZE] Found {len(old_set)} reference markers and {len(new_set)} new tracks to inspect."
    )

    # ======= HIER: Ihre bestehende Distanzprüfung / Lösch-Schleifen auf new_set gegen old_set =======
    removed = 0
    kept = 0
    checked = 0
    skipped_no_marker = 0
    skipped_unselected = 0
    deleted_ptrs: list[int] = []

    # TODO: Ihre bestehende Iteration über new_set und Löschlogik unverändert aufrufen.
    # checked/removed/kept/... entsprechend fortschreiben und deleted_ptrs befüllen.

    log(
        f"[DISTANZE] Cleanup complete: removed={removed}, kept={kept}, checked={checked}, "
        f"skipped_no_marker={skipped_no_marker}, skipped_unselected={skipped_unselected}"
    )
    return {
        "status": "OK",
        "frame": frame,
        "removed": int(removed),
        "kept": int(kept),
        "checked_new": int(checked),
        "skipped_no_marker": int(skipped_no_marker),
        "skipped_unselected": int(skipped_unselected),
        "min_distance": float(min_distance) if (min_distance is not None and isfinite(min_distance)) else float(min_distance or 0.0),
        "distance_unit": distance_unit,
        "old_count": int(len(old_set)),
        "new_total": int(len(new_set)),
        "auto_min_used": bool(min_distance is None),
        "deleted": deleted_ptrs,
    }

