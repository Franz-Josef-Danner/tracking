# Helper/split_cleanup.py
# SPDX-License-Identifier: MIT
from __future__ import annotations
import bpy
from typing import Iterable, List, Tuple, Set

from .naming import _safe_name
from .segments import get_track_segments, track_has_internal_gaps
from .mute_ops import mute_marker_path, mute_unassigned_markers


def _disable_estimated_markers(track: bpy.types.MovieTrackingTrack) -> None:
    """Alle 'estimated' Marker in diesem Track hart auf 'disabled' setzen."""
    try:
        for m in getattr(track, "markers", []):
            if getattr(m, "is_estimated", False):
                try:
                    m.mute = True
                except Exception:
                    pass
                try:
                    m.flag |= getattr(bpy.types.MovieTrackingMarker, "DISABLED", 2)
                except Exception:
                    pass
    except Exception:
        pass


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------

def _segments_by_consecutive_frames_unmuted(track) -> List[List[int]]:
    """
    Dope-Sheet-konforme Segmentierung über ungemutete Markerframes.
    Segmentbruch, wenn Frame-Lücke (f != last+1) vorliegt.
    """
    try:
        frames = sorted({
            int(m.frame)
            for m in getattr(track, "markers", [])
            if (
                hasattr(m, "frame") and m.frame is not None
                and not getattr(m, "mute", False)
                and not getattr(m, "is_estimated", False)  # NEW: Estimated als Lücke behandeln
            )
        })
    except Exception:
        frames = []

    if not frames:
        return []

    segs: List[List[int]] = []
    curr: List[int] = [frames[0]]
    for f in frames[1:]:
        diff = int(f) - int(curr[-1])
        missing = diff - 1
        if missing >= 1:
            segs.append(curr)
            curr = [f]
        else:
            curr.append(f)
    if curr:
        segs.append(curr)
    return segs


def _segment_lengths_unmuted(track: bpy.types.MovieTrackingTrack) -> List[int]:
    """Ermittelt Längen aller un-gemuteten, zusammenhängenden Segmente in Markeranzahl."""
    segs = list(get_track_segments(track))
    fb = _segments_by_consecutive_frames_unmuted(track)
    if len(fb) > len(segs):
        segs = fb

    lengths: List[int] = []
    for seg in segs:
        count = 0
        for m in getattr(track, "markers", []):
            try:
                # NEW: Estimated/Muted grundsätzlich nicht zählen
                if getattr(m, "mute", False) or getattr(m, "is_estimated", False):
                    continue
                f = getattr(m, "frame", None)
                if f is None:
                    continue
                if isinstance(seg, (list, tuple)):
                    if len(seg) and isinstance(seg[0], int):
                        if int(f) in seg:
                            count += 1
                    else:
                        if m in seg:
                            count += 1
            except Exception:
                pass
        lengths.append(count)
    return lengths


def _delete_tracks_by_max_unmuted_seg_len(
    context, tracks: Iterable[bpy.types.MovieTrackingTrack], min_len: int
) -> int:
    """Löscht Tracks, deren längstes un-gemutetes Segment < min_len ist."""
    clip = getattr(getattr(context, "space_data", None), "clip", None)
    if clip is None:
        return 0

    deleted = 0
    survivors = []
    for t in list(tracks):
        try:
            max_len = max(_segment_lengths_unmuted(t)) if t else 0
            if max_len < int(min_len):
                clip.tracking.tracks.remove(t)
                deleted += 1
            else:
                survivors.append(t)
        except Exception:
            survivors.append(t)
    return deleted


def _apply_keep_only_segment(
    track: bpy.types.MovieTrackingTrack,
    seg: List[int],
    *, area, region, space, window
) -> None:
    """Hält genau das gegebene Segment frei (vorher/nachher muten)."""
    if not seg:
        return
    f_start = seg[0] if isinstance(seg[0], int) else getattr(seg[0], "frame", None)
    f_end   = seg[-1] if isinstance(seg[-1], int) else getattr(seg[-1], "frame", None)
    if f_start is None or f_end is None:
        return
    with bpy.context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        mute_marker_path(track, int(f_start) - 1, 'backward', mute=True)
        mute_marker_path(track, int(f_end) + 1, 'forward',  mute=True)


def _delete_all_segments_after_first(
    track: bpy.types.MovieTrackingTrack,
    *, area, region, space, window,
    gap_frames: int = 1,
) -> None:
    """
    Behält im Track nur das **erste** Segment und löscht alle Marker **hinter** diesem Segment
    (beginnend ab f_last + gap_frames).
    """
    segs = _segments_by_consecutive_frames_unmuted(track)
    if len(segs) <= 1:
        return
    keep = segs[0]
    if not keep:
        return
    f_last = int(keep[-1])
    start_cut = f_last + (gap_frames if isinstance(gap_frames, int) and gap_frames > 0 else 1)

    with bpy.context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        for m in list(track.markers)[::-1]:
            try:
                f = int(getattr(m, "frame", -10))
                if f >= start_cut:
                    track.markers.delete_frame(f)
            except Exception:
                pass


def _delete_first_segment(
    track: bpy.types.MovieTrackingTrack,
    *, area, region, space, window,
    gap_frames: int = 1,
) -> None:
    """
    Löscht das **erste** Segment (hart), ohne Marker des nachfolgenden Segments zu berühren.
    """
    segs = _segments_by_consecutive_frames_unmuted(track)
    if len(segs) <= 0:
        return
    first = segs[0]
    if not first:
        return

    with bpy.context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        for m in list(track.markers)[::-1]:
            try:
                f = int(getattr(m, "frame", -10))
                if f in first:
                    track.markers.delete_frame(f)
            except Exception:
                pass


def _dup_once_with_ui(context, area, region, space, track) -> bpy.types.MovieTrackingTrack | None:
    """Dupliziert **einmal** via copy/paste und liefert die neue Kopie (oder None)."""
    clip = space.clip
    window = context.window
    with context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        try:
            for t in clip.tracking.tracks:
                t.select = False
            track.select = True
            names_before = {t.name for t in clip.tracking.tracks}
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            new_track = None
            for t in clip.tracking.tracks:
                if t.name not in names_before:
                    new_track = t
                    break
        except Exception:
            new_track = None
        try:
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            region.tag_redraw()
        except Exception:
            pass
        return new_track


# ------------------------------------------------------------
# Iteratives Duplizieren & Abschälen
# ------------------------------------------------------------

def _iterative_segment_split(context, area, region, space, seed_tracks: Iterable[bpy.types.MovieTrackingTrack]) -> None:
    """
    Phase 1: Startliste duplizieren; im Original alles nach dem ersten Segment löschen.
    Phase 2: Wiederholt erstes Segment löschen, duplizieren, im Original wieder nach dem ersten Segment löschen,
             bis keine Tracks mit >= 1 Segment existieren.
    """
    clip = space.clip
    window = context.window

    # Phase 1
    start_list = list(seed_tracks)
    for tr in list(start_list):
        _disable_estimated_markers(tr)
        segs = _segments_by_consecutive_frames_unmuted(tr)
        if len(segs) >= 1:
            new_tr = _dup_once_with_ui(context, area, region, space, tr)
            if new_tr:
                # keine Logik nötig; Duplikat existiert
                pass
            # Wichtig: unabhängig vom Duplikat im Original beschneiden
            _delete_all_segments_after_first(tr, area=area, region=region, space=space, window=window)

    # Phase 2
    rounds = 0
    while True:
        rounds += 1
        # NEW: Sicherheit – in jeder Runde estimated Marker deaktivieren,
        # damit sie garantiert als Lücken wirken (UI-konsistent).
        for t in list(clip.tracking.tracks):
            _disable_estimated_markers(t)
        candidates = [t for t in list(clip.tracking.tracks)
                      if len(_segments_by_consecutive_frames_unmuted(t)) >= 1]
        if not candidates:
            break

        for tr in candidates:
            _delete_first_segment(tr, area=area, region=region, space=space, window=window)

        dupe_candidates = [t for t in candidates
                           if len(_segments_by_consecutive_frames_unmuted(t)) >= 1 and len(list(t.markers)) > 0]

        for tr in dupe_candidates:
            new_tr = _dup_once_with_ui(context, area, region, space, tr)
            if new_tr:
                pass

        for tr in dupe_candidates:
            _delete_all_segments_after_first(tr, area=area, region=region, space=space, window=window)

        try:
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            region.tag_redraw()
        except Exception:
            pass


# ------------------------------------------------------------
# Öffentliche Hauptfunktion
# ------------------------------------------------------------

def recursive_split_cleanup(context, area, region, space, tracks):
    scene = context.scene
    clip = space.clip
    if clip is None:
        return {'CANCELLED'}

    # Audit vor dem Split (keine Ausgabe, nur Konsistenz)
    for t in tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb

    # Iteratives Duplizieren & Abschälen
    try:
        _iterative_segment_split(context, area, region, space, tracks)
    except Exception:
        pass

    # Audit nach Split
    for t in clip.tracking.tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb

    # Delete-Policy
    try:
        min_len = int(scene.get("tco_min_seg_len", 25))
    except Exception:
        min_len = 25
    _ = _delete_tracks_by_max_unmuted_seg_len(context, clip.tracking.tracks, min_len=min_len)

    # Audit nach Delete (intern)
    leftover_multi = 0
    for t in clip.tracking.tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        if len(segs) >= 1:
            leftover_multi += 1

    # Safety
    mute_unassigned_markers(clip.tracking.tracks)

    return {'FINISHED'}
