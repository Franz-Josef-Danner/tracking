"""
track_length_helper
====================

This helper provides a small utility for computing the total length of
tracked segments for a set of selected markers in Blender’s Movie Clip
Editor.  In the context of the auto‑calibration process, a “tracked
segment” is defined as the contiguous sequence of frames beginning at
the frame where tracking starts (the playhead position) and ending at
the last frame on which a marker still exists for that track.  For each
selected track we measure the distance between the start frame and the
maximum frame index of its markers.  These per‑track lengths are then
summed to produce a single scalar value representing how long the
tracking operator was able to follow all selected markers.

Usage example::

    import bpy
    from .track_length_helper import get_total_track_length

    # Assume tracking has just been run from frame ``start_frame``.
    total_len = get_total_track_length(bpy.context, start_frame)
    print(f"Total tracked frames: {total_len}")

Note
----
This helper does not attempt to determine whether a track contains
multiple disjoint segments.  If a track contains gaps (frames without
a marker), those gaps are implicitly counted in the length because the
distance between the first and last marker frame is used.  This simple
metric is adequate for the auto‑calibration procedure where the goal is
to maximise the overall span of frames tracked, not the number of
continuous frames.
"""

from __future__ import annotations

import bpy

def get_total_track_length(context: bpy.types.Context, start_frame: int) -> int:
    """Return the sum of tracked segment lengths for all selected tracks.

    Parameters
    ----------
    context : bpy.types.Context
        The Blender context from which to derive the current clip and
        selection of tracks.  Selected tracks are determined by the
        ``select`` property on each ``MovieTrackingTrack``.
    start_frame : int
        The frame at which tracking began.  Lengths are measured
        relative to this frame.

    Returns
    -------
    int
        The sum of (max_frame - start_frame + 1) for each selected track
        that contains at least one marker at or beyond ``start_frame``.
    """
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return 0
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return 0

    total_length = 0
    # Iterate over tracks that are currently selected.  The selection is
    # controlled externally by the calling operator.
    for tr in tracking.tracks:
        if not getattr(tr, "select", False):
            continue
        # Gather all marker frame numbers on or after start_frame.  We
        # assume marker frames are sorted in ascending order as
        # maintained by Blender.
        marker_frames = [mk.frame for mk in tr.markers if mk.frame >= start_frame]
        if not marker_frames:
            continue
        max_frame = max(marker_frames)
        # Length is inclusive: if the last marker is on the same frame as
        # start_frame the length is 1.
        total_length += (max_frame - start_frame + 1)
    return total_length