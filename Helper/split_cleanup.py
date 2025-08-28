# Helper/split_cleanup.py
# SPDX-License-Identifier: MIT
from __future__ import annotations
import bpy
from typing import Iterable, List, Tuple, Set

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
