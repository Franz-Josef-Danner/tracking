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

def _segment_lengths_unmuted(track: bpy.types.MovieTrackingTrack) -> List[int]:
    """Ermittelt Längen aller un-gemuteten, zusammenhängenden Segmente in Markeranzahl."""
    segs = list(get_track_segments(track))
    lengths = []
    for seg in segs:
        count = 0
        for m in getattr(track, "markers", []):
            try:
                if m.mute:
                    continue
                f = getattr(m, "frame", None)
                if f is None:
                    continue
                if isinstance(seg, (list, tuple)):
                    if len(seg) and isinstance(seg[0], int):
                        if f in seg:
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

def _rebind_tracks_by_name(clip) -> dict:
    by_name = {}
    for t in clip.tracking.tracks:
        tn = _safe_name(t)
        if tn:
            by_name[tn] = t
    return by_name

def _apply_keep_only_segment(
    track: bpy.types.MovieTrackingTrack,
    seg: List[int],
    *, area, region, space
) -> None:
    """Hält genau das gegebene Segment frei (vorher/nachher muten)."""
    if not seg:
        return
    f_start = seg[0] if isinstance(seg[0], int) else getattr(seg[0], "frame", None)
    f_end   = seg[-1] if isinstance(seg[-1], int) else getattr(seg[-1], "frame", None)
    if f_start is None or f_end is None:
        return
    mute_marker_path(track, int(f_start) - 1, 'backward', mute=True)
    mute_marker_path(track, int(f_end) + 1, 'forward',  mute=True)

# ------------------------------------------------------------
# Neuer Kern: Exakte Segment-Splittung
# ------------------------------------------------------------

def _split_track_into_exact_segments(context, area, region, space, track) -> List[bpy.types.MovieTrackingTrack]:
    """Erzeugt für jeden Track mit N Segmenten genau N Tracks – jeweils mit EINEM aktiven Segment."""
    scene = context.scene
    clip = space.clip
    segs = list(get_track_segments(track))
    if len(segs) <= 1:
        return [track]

    copies_needed = len(segs) - 1

    with context.temp_override(area=area, region=region, space_data=space):
        try:
            for t in clip.tracking.tracks:
                t.select = False
            track.select = True
        except Exception:
            pass

        for _ in range(copies_needed):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()

        deps = context.evaluated_depsgraph_get()
        deps.update()
        bpy.context.view_layer.update()
        scene.frame_set(scene.frame_current)

    by_name = _rebind_tracks_by_name(clip)
    base = _safe_name(track)
    group = [t for n, t in by_name.items() if _safe_name(n) == base]
    if not group:
        group = [track]

    group_sorted = []
    if track in group:
        group_sorted.append(track)
    group_sorted.extend([t for t in group if t is not track])

    k = min(len(group_sorted), len(segs))
    with context.temp_override(area=area, region=region, space_data=space):
        for i in range(k):
            _apply_keep_only_segment(group_sorted[i], segs[i], area=area, region=region, space=space)

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
        print(f"[Audit-BEFORE] Track='{t.name}' segs={len(segs)} lens={[len(s) for s in segs]}")

    # 1) Split
    result_tracks = []
    for t in list(tracks):
        try:
            segs = list(get_track_segments(t))
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
        print(f"[Audit-AFTER_SPLIT] Track='{t.name}' segs={len(segs)} lens={[len(s) for s in segs]}")

    # 2) Delete-Policy
    try:
        min_len = int(scene.get("tco_min_seg_len", 25))
    except Exception:
        min_len = 25
    deleted = _delete_tracks_by_max_unmuted_seg_len(context, clip.tracking.tracks, min_len=min_len)
    print(f"[Audit-DELETE] deleted={deleted}")

    # --- Audit nach Delete ---
    for t in clip.tracking.tracks:
        segs = list(get_track_segments(t))
        if len(segs) > 1:
            print(f"[Audit-LEFTOVER] Track='{t.name}' segs={len(segs)} lens={[len(s) for s in segs]}")

    # 3) Safety
    from .mute_ops import mute_unassigned_markers
    mute_unassigned_markers(clip.tracking.tracks)

    print("[SplitCleanup] recursive_split_cleanup: FINISHED")
    return {'FINISHED'}

