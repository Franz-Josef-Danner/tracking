# Helper/split_cleanup.py
# SPDX-License-Identifier: MIT
from __future__ import annotations
import bpy
from typing import Iterable, List

from .naming import _safe_name
from .segments import get_track_segments, track_has_internal_gaps
from .mute_ops import mute_marker_path, mute_unassigned_markers

_VERBOSE_SCENE_KEY = "tco_verbose_split"


def _is_verbose(scene) -> bool:
    try:
        return bool(scene.get(_VERBOSE_SCENE_KEY, False))
    except Exception:
        return False


def _log(scene, msg: str) -> None:
    if _is_verbose(scene):
        print(f"[SplitCleanup] {msg}")


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------

def _segments_by_consecutive_frames_unmuted(track) -> List[List[int]]:
    """
    Robust: Segmentierung strikt nach Frame-Kontinuität (nur ungemutete Marker).
    Jede Lücke (frame != last + 1) startet ein neues Segment.
    Rückgabe: Liste von Frame-Listen.
    """
    frames = []
    try:
        for m in getattr(track, "markers", []):
            if getattr(m, "mute", False):
                continue
            f = getattr(m, "frame", None)
            if f is not None:
                frames.append(int(f))
    except Exception:
        return []

    frames = sorted(set(frames))
    if not frames:
        return []

    segs: List[List[int]] = []
    curr = [frames[0]]
    for f in frames[1:]:
        if f == curr[-1] + 1:
            curr.append(f)
        else:
            segs.append(curr)
            curr = [f]
    if curr:
        segs.append(curr)
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
                if getattr(m, "mute", False):
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


# ------------------------------------------------------------
# Neuer Kern: Exakte Segment-Splittung
# ------------------------------------------------------------

def _split_track_into_exact_segments(context, area, region, space, track) -> List[bpy.types.MovieTrackingTrack]:
    """
    Erzeugt für jeden Track mit N Segmenten genau N Tracks – jeweils mit EINEM aktiven Segment.
    Nutzt get_track_segments(...) und fällt bei zu grober Erkennung auf die
    Frame-Kontinuitäts-Segmente zurück.
    """
    scene = context.scene
    clip = space.clip
    window = context.window

    # 1) Segmente bestimmen (primär API, Fallback bei „grobem“ Ergebnis)
    segs = list(get_track_segments(track))
    fb_segs = _segments_by_consecutive_frames_unmuted(track)
    if len(fb_segs) > len(segs):
        segs = fb_segs

    if len(segs) <= 1:
        return [track]

    copies_needed = len(segs) - 1

    # 2) Duplikate erzeugen (mit vollem UI-Kontext)
    with context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        try:
            for t in clip.tracking.tracks:
                t.select = False
            track.select = True
        except Exception:
            pass

        for _ in range(copies_needed):
            try:
                bpy.ops.clip.copy_tracks()
                bpy.ops.clip.paste_tracks()
            except Exception as ex:
                _log(scene, f"copy/paste failed: {ex!r}")

        deps = context.evaluated_depsgraph_get()
        deps.update()
        bpy.context.view_layer.update()
        scene.frame_set(scene.frame_current)

    # 3) Kopien finden: per _safe_name() Prefix-Match (inkl. .001/.002 usw.)
    base = _safe_name(track)
    group: List[bpy.types.MovieTrackingTrack] = []
    try:
        for t in clip.tracking.tracks:
            nm = _safe_name(t)
            if nm and nm.startswith(base):
                group.append(t)
    except Exception:
        pass
    if not group:
        group = [track]

    # Original zuerst, Kopien danach (stabile Reihenfolge)
    group_sorted: List[bpy.types.MovieTrackingTrack] = []
    if track in group:
        group_sorted.append(track)
    group_sorted.extend([t for t in group if t is not track])

    # 4) Pro Kopie genau ein Segment aktiv lassen, Rest muten
    k = min(len(group_sorted), len(segs))
    with context.temp_override(
        window=window, screen=window.screen if window else None,
        area=area, region=region, space_data=space
    ):
        for i in range(k):
            _apply_keep_only_segment(group_sorted[i], segs[i], area=area, region=region, space=space, window=window)

        for j in range(k, len(group_sorted)):
            try:
                clip.tracking.tracks.remove(group_sorted[j])
            except Exception:
                pass

        deps = context.evaluated_depsgraph_get()
        deps.update()
        bpy.context.view_layer.update()
        region.tag_redraw()

    _log(scene, f"split: '{track.name}' → segments={len(segs)} → tracks={k}")
    return group_sorted[:k]


# ------------------------------------------------------------
# Öffentliche Hauptfunktion
# ------------------------------------------------------------

def recursive_split_cleanup(context, area, region, space, tracks):
    scene = context.scene
    print("[SplitCleanup] recursive_split_cleanup: start")

    clip = space.clip
    if clip is None:
        return {'CANCELLED'}

    # --- Audit vor dem Split ---
    for t in tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        print(f"[Audit-BEFORE] Track='{t.name}' segs={len(segs)} lens={[len(s) for s in segs]}")

    # 1) Split (mit Fallback)
    result_tracks: List[bpy.types.MovieTrackingTrack] = []
    for t in list(tracks):
        try:
            segs = list(get_track_segments(t))
            fb = _segments_by_consecutive_frames_unmuted(t)
            if len(fb) > len(segs):
                segs = fb
            if len(segs) <= 1:
                result_tracks.append(t)
            else:
                result_tracks.extend(_split_track_into_exact_segments(context, area, region, space, t))
        except Exception as e:
            print(f"[Audit-ERROR] Split fail track={t.name}: {e}")
            result_tracks.append(t)

    # --- Audit nach Split ---
    for t in result_tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        print(f"[Audit-AFTER_SPLIT] Track='{t.name}' segs={len(segs)} lens={[len(s) for s in segs]}")

    # 1b) Hard-Enforcement: bis zu 2 zusätzliche Pässe für etwaige Reste
    max_extra_passes = 2
    for pass_idx in range(max_extra_passes):
        leftovers = [t for t in list(clip.tracking.tracks)
                     if len(_segments_by_consecutive_frames_unmuted(t)) > 1]
        if not leftovers:
            break
        print(f"[Enforce] extra pass {pass_idx+1}: splitting {len(leftovers)} leftover track(s)")
        new_result: List[bpy.types.MovieTrackingTrack] = []
        for t in leftovers:
            try:
                new_result.extend(_split_track_into_exact_segments(context, area, region, space, t))
            except Exception as e:
                print(f"[Enforce-ERROR] Split fail track={t.name}: {e}")
                new_result.append(t)
        result_tracks = new_result  # für spätere Audits

    # --- Audit nach Enforcement ---
    for t in clip.tracking.tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        print(f"[Audit-ENFORCED] Track='{t.name}' segs={len(segs)} lens={[len(s) for s in segs]}")

    # 2) Delete-Policy
    try:
        min_len = int(scene.get("tco_min_seg_len", 25))
    except Exception:
        min_len = 25
    deleted = _delete_tracks_by_max_unmuted_seg_len(context, clip.tracking.tracks, min_len=min_len)
    print(f"[Audit-DELETE] deleted={deleted}")

    # --- Audit nach Delete ---
    leftover_multi = 0
    for t in clip.tracking.tracks:
        segs = list(get_track_segments(t))
        fb = _segments_by_consecutive_frames_unmuted(t)
        if len(fb) > len(segs):
            segs = fb
        if len(segs) > 1:
            leftover_multi += 1
            print(f"[Audit-LEFTOVER] Track='{t.name}' segs={len(segs)} lens={[len(s) for s in segs]}")
    if leftover_multi == 0:
        print("[Audit-LEFTOVER] none")

    # 3) Safety
    mute_unassigned_markers(clip.tracking.tracks)

    print("[SplitCleanup] recursive_split_cleanup: FINISHED")
    return {'FINISHED'}
