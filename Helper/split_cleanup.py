# Helper/split_cleanup.py
# SPDX-License-Identifier: MIT
from __future__ import annotations
import bpy
from typing import Iterable, List, Tuple, Set

from .naming import _safe_name
from .segments import get_track_segments, track_has_internal_gaps
from .mute_ops import mute_marker_path, mute_unassigned_markers

_VERBOSE_SCENE_KEY = "tco_verbose_split"

def _disable_estimated_markers(track: bpy.types.MovieTrackingTrack) -> None:
    """Alle 'estimated' Marker in diesem Track hart auf 'disabled' setzen."""
    try:
        for m in getattr(track, "markers", []):
            # Manche Builds haben direkt is_estimated, andere nur über Flag-Logik
            if getattr(m, "is_estimated", False):
                # Marker stumm/disabled setzen
                try:
                    m.mute = True
                except Exception:
                    pass
                # Flag DISABLED zusätzlich setzen, falls vorhanden
                try:
                    m.flag |= getattr(bpy.types.MovieTrackingMarker, "DISABLED", 2)
                except Exception:
                    pass
    except Exception:
        pass


def _is_verbose(scene) -> bool:
    try:
        return bool(scene.get(_VERBOSE_SCENE_KEY, False))
    except Exception:
        return False


def _log(scene, msg: str) -> None:
    if _is_verbose(scene):
        pass

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------

def _segments_by_consecutive_frames_unmuted(track) -> List[List[int]]:
    """
    Segmentierung nach Frame-Kontinuität, nur mit 'tracked'-Markern.
    'estimated' Marker werden explizit als Lücke gewertet.
    """
    segs: List[List[int]] = []
    curr: List[int] = []

    try:
        for m in sorted(getattr(track, "markers", []), key=lambda mm: int(mm.frame)):
            f = int(getattr(m, "frame", -1))
            if f < 0:
                continue

            # --- Status prüfen ---
            # Flag (Bitmask), mute und is_estimated sind die entscheidenden Kriterien
            flag = getattr(m, "flag", 0)
            mute = getattr(m, "mute", False)
            est  = bool(getattr(m, "is_estimated", False))  # manche Builds nennen es auch 'estimated'

            # gültig nur, wenn Marker tracked UND nicht muted
            is_tracked = (not mute) and not est and (flag & 1)  # Bit0 == TRACKED

            if is_tracked:
                # wenn Segment leer → neu anfangen
                if not curr:
                    curr = [f]
                else:
                    # fortlaufend?
                    if f == curr[-1] + 1:
                        curr.append(f)
                    else:
                        segs.append(curr)
                        curr = [f]
            else:
                # estimated oder disabled → Segmentende erzwingen
                if curr:
                    segs.append(curr)
                    curr = []
        # nach der Schleife Rest anhängen
        if curr:
            segs.append(curr)

    except Exception:
        return []

    return segs



def _segment_lengths_unmuted(track: bpy.types.MovieTrackingTrack) -> List[int]:
    """Ermittelt Längen aller un-gemuteten, zusammenhängenden Segmente in Markeranzahl."""
    segs = list(get_track_segments(track))
    # Fallback nutzen, falls get_track_segments zu grob ist
    fb = _segments_by_consecutive_frames_unmuted(track)
    if len(fb) > len(segs):
        segs = fb

    lengths: List[int] = []
    for seg in segs:
        count = 0
        for m in getattr(track, "markers", []):
            try:
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
    scene = context.scene
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

    _log(scene, f"final: delete_by_unmuted_len(min_len={min_len}) → deleted={deleted}")
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
    """Behält im Track nur das **erste** Segment (ungemutete Kontinuität) und
    löscht alle Marker **mit Sicherheitsabstand** *nach* diesem Segment.

    Es bleibt mindestens ``gap_frames`` Abstand nach dem letzten Frame des
    ersten Segments bestehen. D. h. bei ``gap_frames=1`` beginnt das Löschen
    frühestens ab ``f_last + 1``.
    """
    segs = _segments_by_consecutive_frames_unmuted(track)
    if len(segs) <= 1:
        return
    keep = segs[0]
    if not keep:
        return
    f_last = int(keep[-1])
    # Start der Löschung **hinter** dem Segment mit min. gap
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
    """Löscht das **erste** Segment (ungemutete Kontinuität) hart (Marker DELETE)
    und wahrt einen Mindestabstand von ``gap_frames`` zum nächsten Segment.

    Hinweis: Bei normaler Segmentierung (dt>1 zwischen Segmenten) ist der
    Abstand ohnehin ≥ 1. Die Logik klemmt die Löschgrenze zusätzlich so,
    dass niemals Marker des nachfolgenden Segments versehentlich entfernt werden.
    """
    segs = _segments_by_consecutive_frames_unmuted(track)
    if len(segs) <= 0:
        return

    first = segs[0]
    if not first:
        return

    # Standard-Löschgrenze: letztes Frame des ersten Segments
    limit = int(first[-1])

    # Falls es ein zweites Segment gibt, stelle sicher, dass wir die Frames
    # innerhalb der Sicherheitszone **vor** dessen Start nicht überschreiten.
    if len(segs) >= 2:
        start2 = int(segs[1][0])
        max_del = start2 - (gap_frames if isinstance(gap_frames, int) and gap_frames > 0 else 1) - 1
        if max_del < limit:
            limit = max_del

    with bpy.context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        for m in list(track.markers)[::-1]:
            try:
                f = int(getattr(m, "frame", -10))
                # Mute-Status wird bewusst ignoriert: harte Segmenttrennung gewünscht.
                # Nur Frames des ersten Segments löschen und nie über die Grenze
                if f in first and f <= limit:
                    track.markers.delete_frame(f)
            except Exception:
                pass


def _dup_once_with_ui(context, area, region, space, track) -> bpy.types.MovieTrackingTrack | None:
    """Dupliziert **genau einmal** via copy/paste und liefert die neue Kopie (oder None)."""
    clip = space.clip
    window = context.window
    with context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        try:
            # Selektion sauber setzen
            for t in clip.tracking.tracks:
                t.select = False
            track.select = True
            # Namen vorab merken
            names_before = {t.name for t in clip.tracking.tracks}
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            # neue finden
            new_track = None
            for t in clip.tracking.tracks:
                if t.name not in names_before:
                    new_track = t
                    break
        except Exception as ex:
            _log(context.scene, f"copy/paste failed: {ex!r}")
            new_track = None
        # sanft UI/Depsgraph refresh
        try:
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            region.tag_redraw()
        except Exception:
            pass
        return new_track


# ------------------------------------------------------------
# Neuer Kern: Iteratives Duplizieren & Abschälen (Schritt 1 + 2)
# ------------------------------------------------------------

def _iterative_segment_split(context, area, region, space, seed_tracks: Iterable[bpy.types.MovieTrackingTrack]) -> None:
    """
    Implementiert die vom Nutzer geforderte 2-Phasen-Logik:
      1) Startliste einfrieren, betroffene Tracks **einmal duplizieren**,
         im **Original** alle Segmente **nach dem ersten** löschen.
      2) Danach wiederholt:
           - in **allen** Tracks mit >1 Segment das **erste Segment löschen**
           - diese Tracks **einmal duplizieren**
           - im **Original** wieder alle Segmente **nach dem ersten** löschen
         bis keine Tracks mit >1 Segment existieren.
    """
    scene = context.scene
    clip = space.clip
    window = context.window

    # -------- Phase 1: Startliste einfrieren --------
    start_list = list(seed_tracks)
    _log(scene, f"IterSplit: phase-1 seed_count={len(start_list)}")
    for tr in list(start_list):
        # Ergänzung: zuerst alle 'estimated' Marker auf disabled setzen
        _disable_estimated_markers(tr)
        segs = _segments_by_consecutive_frames_unmuted(tr)
        if len(segs) > 1:
            new_tr = _dup_once_with_ui(context, area, region, space, tr)
            if new_tr:
                _log(scene, f"IterSplit: dup '{tr.name}' → '{new_tr.name}' (phase-1)")
            _delete_all_segments_after_first(tr, area=area, region=region, space=space, window=window)

    # -------- Phase 2: Wiederholung bis stabil --------
    rounds = 0
    while True:
        rounds += 1
        # Kandidaten: alle aktuellen Tracks mit >1 Segment (ungemutet)
        candidates = [t for t in list(clip.tracking.tracks)
                      if len(_segments_by_consecutive_frames_unmuted(t)) > 1]
        if not candidates:
            _log(scene, f"IterSplit: converged after {rounds-1} round(s)")
            break

        _log(scene, f"IterSplit: round {rounds} candidates={len(candidates)}")

        # 2a) In allen Kandidaten zuerst das **erste Segment löschen**
        for tr in candidates:
            _delete_first_segment(tr, area=area, region=region, space=space, window=window)

        # --- Wichtiger Zwischenschritt ---
        # Nach dem Entfernen des ersten Segments haben einige Tracks evtl. nur noch
        # EIN Segment oder gar keine Marker mehr. Nur solche mit weiterhin >1 Segmenten
        # werden dupliziert und anschließend beschnitten. So vermeiden wir "leere" Duplikate
        # und das unerwünschte Kürzen von stabilen Ein-Segment-Tracks.
        dupe_candidates = [t for t in candidates
                           if len(_segments_by_consecutive_frames_unmuted(t)) > 1 and len(list(t.markers)) > 0]
        _log(scene, f"IterSplit: round {rounds} post-delete → dupe_candidates={len(dupe_candidates)}")

        # 2b) Danach nur diese Kandidaten **einmal duplizieren**
        dup_map = {}
        for tr in dupe_candidates:
            new_tr = _dup_once_with_ui(context, area, region, space, tr)
            if new_tr:
                dup_map[tr] = new_tr
                _log(scene, f"IterSplit: dup '{tr.name}' → '{new_tr.name}' (round {rounds})")

        # 2c) Im **Original** alles nach dem ersten Segment löschen (nur dort, wo >1 Segmente sind)
        for tr in dupe_candidates:
            _delete_all_segments_after_first(tr, area=area, region=region, space=space, window=window)

        # sanfter Refresh
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

    # --- Audit vor dem Split ---
    for t in tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb

    # 1) Neuer Kern: Iteratives Duplizieren & Abschälen
    try:
        _iterative_segment_split(context, area, region, space, tracks)
    except Exception as e:
        # Fallback: nichts tun, weiter mit Delete-Policy
        pass
    # --- Audit nach Split ---
    for t in clip.tracking.tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb

    # (Enforcement entfällt; die Iteration konvergiert bis keine Multi-Segments mehr da sind)
    # --- Audit nach Enforcement ---
    for t in clip.tracking.tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb

    # 2) Delete-Policy
    try:
        min_len = int(scene.get("tco_min_seg_len", 25))
    except Exception:
        min_len = 25
    deleted = _delete_tracks_by_max_unmuted_seg_len(context, clip.tracking.tracks, min_len=min_len)

    # --- Audit nach Delete ---
    leftover_multi = 0
    for t in clip.tracking.tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        if len(segs) > 1:
            leftover_multi += 1
    if leftover_multi == 0:
        pass
    # 3) Safety
    mute_unassigned_markers(clip.tracking.tracks)

    return {'FINISHED'}
