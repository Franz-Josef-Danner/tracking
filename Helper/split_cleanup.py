# Helper/split_cleanup.py
# SPDX-License-Identifier: MIT
from __future__ import annotations
import bpy
from typing import Iterable, List, Tuple, Set, Dict, Any, Optional

from .naming import _safe_name
from .segments import get_track_segments, track_has_internal_gaps
from .mute_ops import mute_marker_path, mute_unassigned_markers

# --------------------------------------------------------------------------
# Console logging
# --------------------------------------------------------------------------
# All console outputs in this module are disabled.  To aid debugging without
# writing to stdout, use the no-op `_log` function instead of `print`.
def _log(*args: Any, **kwargs: Any) -> None:
    """No-op debug logger. Replace calls to print with this to silence output."""
    # Intentionally do nothing to suppress console output.
    return None


def _disable_estimated_markers(track: bpy.types.MovieTrackingTrack) -> None:
    """Alle 'estimated' Marker in diesem Track hart auf 'disabled' setzen."""
    try:
        cnt = 0
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
                cnt += 1
        if bpy.context and getattr(bpy.context, "scene", None) and bpy.context.scene.get("tco_debug_split", True):
            # Silence console output by routing through the no-op logger.
            _log(f"[SplitDBG][disable_estimated] track={track.name} estimated->muted={cnt}")
    except Exception:
        pass


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------

def _dbg_enabled() -> bool:
    try:
        sc = getattr(bpy.context, "scene", None)
        return bool(sc is None or sc.get("tco_debug_split", True))
    except Exception:
        return True


def _snapshot_track(track) -> dict:
    try:
        markers = list(getattr(track, "markers", []))
        frames_all = sorted({int(getattr(m, "frame", -10)) for m in markers})
        muted = sum(1 for m in markers if getattr(m, "mute", False))
        est = sum(1 for m in markers if getattr(m, "is_estimated", False))
        return {
            "markers": len(markers),
            "frames": len(frames_all),
            "muted": muted,
            "estimated": est,
            "frames_head": frames_all[:8],
            "frames_tail": frames_all[-8:],
        }
    except Exception:
        return {}


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
    if _dbg_enabled():
        try:
            # Silence console output via the no-op logger.
            _log(
                f"[SegDBG][unmuted_segments] track={track.name} "
                f"unmuted_frames={len(frames)} segs={len(segs)} "
                f"sample0={segs[0][:8] if segs else []}"
            )
        except Exception:
            pass
    return segs


def _keep_exact_frames(
    track: bpy.types.MovieTrackingTrack,
    keep_frames: Set[int],
    *, area, region, space, window
) -> None:
    """
    Harter Zuschnitt auf eine exakte Frame-Menge:
    - Löscht alle Marker, deren Frame **nicht** in keep_frames liegt.
    - Unmutet die verbleibenden Marker zur Sichtbarkeitskonsistenz.
    """
    if not keep_frames:
        return
    with bpy.context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        if _dbg_enabled():
            snap_before = _snapshot_track(track)
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][keep_exact] track={track.name} keep={len(keep_frames)} "
                f"keep_head={sorted(list(keep_frames))[:8]}"
            )
        for m in list(track.markers)[::-1]:
            try:
                f = int(getattr(m, "frame", -10))
                if f not in keep_frames:
                    track.markers.delete_frame(f)
            except Exception:
                pass
        for m in getattr(track, "markers", []):
            try:
                if int(getattr(m, "frame", -10)) in keep_frames:
                    m.mute = False
            except Exception:
                pass
        if _dbg_enabled():
            segs_all = list(get_track_segments(track))
            segs_unm = _segments_by_consecutive_frames_unmuted(track)
            snap_after = _snapshot_track(track)
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][keep_exact][post] track={track.name} "
                f"segs_all={len(segs_all)} segs_unmuted={len(segs_unm)} "
                f"snapshot_before={snap_before} snapshot_after={snap_after}"
            )


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
        delcnt = 0
        for m in list(track.markers)[::-1]:
            try:
                f = int(getattr(m, "frame", -10))
                if f >= start_cut:
                    track.markers.delete_frame(f)
                    delcnt += 1
            except Exception:
                pass
        if _dbg_enabled():
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][delete_after_first] track={track.name} "
                f"first_last={f_last} start_cut={start_cut} deleted={delcnt}"
            )


def _trim_to_first_unmuted_segment(
    track: bpy.types.MovieTrackingTrack,
    *, area, region, space, window,
) -> None:
    """
    Harter, idempotenter Trim:
    - Bestimme das erste unmuted Segment (estimated gilt als Lücke)
    - Behalte **nur** exakt dessen Frames; lösche alle anderen Frames (vorher, nachher, in-range Fremdframes)
    """
    segs = _segments_by_consecutive_frames_unmuted(track)
    if not segs:
        return
    keep_frames = {int(f) for f in segs[0] if isinstance(f, int)}
    if not keep_frames:
        return
    with bpy.context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        delcnt = 0
        for m in list(track.markers)[::-1]:
            try:
                f = int(getattr(m, "frame", -10))
                if f not in keep_frames:
                    track.markers.delete_frame(f)
                    delcnt += 1
            except Exception:
                pass
        # Optional: sichtbare Konsistenz – Keep-Frames unmute
        for m in getattr(track, "markers", []):
            try:
                if int(getattr(m, "frame", -10)) in keep_frames:
                    m.mute = False
            except Exception:
                pass
        if _dbg_enabled():
            segs_all = list(get_track_segments(track))
            segs_unm = _segments_by_consecutive_frames_unmuted(track)
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][trim_first_unmuted] track={track.name} "
                f"keep={len(keep_frames)} deleted={delcnt} "
                f"segs_all={len(segs_all)} segs_unmuted={len(segs_unm)}"
            )


def _delete_first_segment(
    track: bpy.types.MovieTrackingTrack,
    *, area, region, space, window,
    gap_frames: int = 1,
) -> None:
    """
    Löscht das **erste** Segment (hart), ohne Marker des nachfolgenden Segments zu berühren.
    Jetzt werden Marker **im Frame-Bereich** [f_start..f_end] entfernt – unabhängig von mute/is_estimated.
    """
    segs = _segments_by_consecutive_frames_unmuted(track)
    if len(segs) <= 0:
        return
    first = segs[0]
    if not first:
        return
    f_start = int(first[0])
    f_end = int(first[-1])
    with bpy.context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        delcnt = 0
        for m in list(track.markers)[::-1]:
            try:
                f = int(getattr(m, "frame", -10))
                if f_start <= f <= f_end:
                    track.markers.delete_frame(f)
                    delcnt += 1
            except Exception:
                pass
        if _dbg_enabled():
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][delete_first_segment] track={track.name} "
                f"range=[{f_start}..{f_end}] deleted={delcnt}"
            )


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
        if _dbg_enabled():
            # Silence console output via the no-op logger.
            _log(f"[SplitDBG][dup] base={track.name} new={(new_track.name if new_track else None)}")
        try:
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            region.tag_redraw()
        except Exception:
            pass
        return new_track


# ------------------------------------------------------------
# Deterministischer One-Pass Split pro Track
# ------------------------------------------------------------

def _split_track_by_all_segments(
    context, area, region, space, track: bpy.types.MovieTrackingTrack
) -> None:
    """
    Nicht-iterativer, deterministischer Split:
    - Ermittelt alle Segmente **auf Gesamtsicht** (get_track_segments).
    - Dupliziert (k-1)× für k Segmente.
    - Schneidet Original + Duplikate jeweils auf **exakt** ihr Zielsegment (harte Frame-Menge).
    """
    clip = space.clip
    window = context.window
    segs_all = list(get_track_segments(track))  # zählt ALLE Marker (auch muted/estimated)
    if len(segs_all) <= 1:
        return
    if _dbg_enabled():
        # Silence console output via the no-op logger.
        _log(
            f"[SplitDBG][split_by_all] track={track.name} segs={len(segs_all)} "
            f"heads={[s[:3] for s in segs_all[:3]]}"
        )
    # Duplikate erzeugen (für Segmente 1..k-1)
    dup_list: List[bpy.types.MovieTrackingTrack] = []
    for _ in range(1, len(segs_all)):
        new_tr = _dup_once_with_ui(context, area, region, space, track)
        if new_tr:
            dup_list.append(new_tr)
    # Zuordnen: Original → seg[0], Duplikate → seg[1], seg[2], ...
    targets: List[Tuple[bpy.types.MovieTrackingTrack, Set[int]]] = []
    targets.append((track, {int(f) for f in segs_all[0]}))
    for i, d in enumerate(dup_list, start=1):
        if i < len(segs_all):
            targets.append((d, {int(f) for f in segs_all[i]}))
    # Harte Zuschnitte
    for trk, keep in targets:
        _keep_exact_frames(trk, keep, area=area, region=region, space=space, window=window)
        if _dbg_enabled():
            segs_now = list(get_track_segments(trk))
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][split_by_all][post] track={trk.name} segs_now={len(segs_now)}"
            )
    # Depsgraph/UI refresh (defensiv)
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

def _find_clip_editor_override() -> Dict[str, Any]:
    """Suche eine CLIP_EDITOR-Area und baue ein temp_override-Dict.
    Liefert ggf. {} wenn nichts gefunden wird."""
    wm = getattr(bpy.context, "window_manager", None)
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {"window": win, "area": area, "region": region, "space_data": space, "scene": bpy.context.scene}
    return {}

def _resolve_clip(context: bpy.types.Context, space: Optional[Any]) -> Optional[Any]:
    """Robuste Clip-Auflösung."""
    clip = getattr(space, "clip", None) if space else None
    if clip:
        return clip
    clip = getattr(context, "edit_movieclip", None)
    if clip:
        return clip
    try:
        # Fallback: irgendeinen existierenden Clip nehmen
        return next(iter(bpy.data.movieclips)) if bpy.data.movieclips else None
    except Exception:
        return None

def _to_list(value) -> list:
    try:
        return list(value) if value is not None else []
    except Exception:
        return []

def recursive_split_cleanup(context,
                            area: Optional[Any] = None,
                            region: Optional[Any] = None,
                            space: Optional[Any] = None,
                            tracks: Optional[Any] = None,
                            **kwargs):
    """
    Robust callable:
      - Akzeptiert zusätzliche kwargs (z. B. window, space_data, scene) ohne TypeError.
      - Löst fehlende area/region/space via aktivem CLIP_EDITOR oder Kontext/Fallback.
      - Akzeptiert tracks als bpy_prop_collection oder list; None → aus clip.tracking.tracks.
      - Führt No-Op/FINISHED aus, wenn kein Clip gefunden wird oder keine Tracks vorhanden sind.
    """
    # 1) space aliasieren, falls über override gekommen
    if space is None:
        space = kwargs.get("space_data", None)
    # 2) area/region ggf. aus override ziehen
    if area is None:
        area = kwargs.get("area", None)
    if region is None:
        region = kwargs.get("region", None)
    # 3) Wenn nichts vorhanden → einen Clip-Editor suchen
    if space is None or area is None or region is None:
        ov = _find_clip_editor_override()
        area   = area   or ov.get("area")
        region = region or ov.get("region")
        space  = space  or ov.get("space_data")
    # 4) Clip robust auflösen
    clip = _resolve_clip(context, space)
    if clip is None:
        # Kein Clip → sauber abbrechen
        return {'CANCELLED'}
    # 5) Tracks normalisieren
    if tracks is None:
        trk = getattr(clip, "tracking", None)
        tracks = getattr(trk, "tracks", []) if trk else []
    tracks_list = _to_list(tracks)
    if len(tracks_list) == 0:
        # Nichts zu tun → OK zurück
        return {'FINISHED'}
    scene = context.scene

    # Audit vor dem Split (keine Ausgabe, nur Konsistenz)
    for t in tracks_list:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        if _dbg_enabled():
            snap = _snapshot_track(t)
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][pre_audit] track={t.name} segs_all={len(get_track_segments(t))} "
                f"segs_unmuted={len(_segments_by_consecutive_frames_unmuted(t))} snapshot={snap}"
            )

    # Deterministischer One-Pass-Split pro Track
    try:
        for t in list(tracks_list):
            _split_track_by_all_segments(context, area, region, space, t)
    except Exception:
        pass

    # Audit nach Split
    for t in getattr(getattr(clip, "tracking", None), "tracks", []):
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        if _dbg_enabled():
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][post_split_audit] track={t.name} segs_all={len(get_track_segments(t))} "
                f"segs_unmuted={len(_segments_by_consecutive_frames_unmuted(t))}"
            )

    # Delete-Policy
    try:
        min_len = int(scene.get("tco_min_seg_len", 25))
    except Exception:
        min_len = 25
    clip_tracks = getattr(getattr(clip, "tracking", None), "tracks", [])
    del_short = _delete_tracks_by_max_unmuted_seg_len(context, clip_tracks, min_len=min_len)
    if _dbg_enabled():
        # Silence console output via the no-op logger.
        _log(f"[SplitDBG][delete_short] min_len={min_len} deleted={del_short}")

    # Audit nach Delete (intern)
    leftover_multi = 0
    for t in clip_tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        if len(segs) >= 2:
            leftover_multi += 1
        if _dbg_enabled() and len(segs) >= 2:
            # Silence console output via the no-op logger.
            _log(
                f"[SplitDBG][leftover] track={t.name} segs_all={len(get_track_segments(t))} "
                f"segs_unmuted={len(_segments_by_consecutive_frames_unmuted(t))}"
            )

    # Optionaler Hygiene-Pass: sehr kurze Tracks entfernen und Mute-Aufräumung
    try:
        mute_unassigned_markers(clip_tracks)
    except Exception:
        pass
    if _dbg_enabled():
        total = len(list(clip_tracks))
        # Silence console output via the no-op logger.
        _log(f"[SplitDBG][finish] tracks_total={total} leftover_multi={leftover_multi}")

    return {'FINISHED'}
