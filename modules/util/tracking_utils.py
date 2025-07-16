"""Utility helpers for Blender tracking."""

from __future__ import annotations

import bpy


def safe_remove_track(clip, track):
    """Safely remove ``track`` from ``clip``.

    Tries to call :func:`bpy.ops.clip.track_remove` in a Clip Editor UI
    context. If the operator cannot be executed, falls back to directly
    removing the track from ``clip.tracking.tracks``.
    """
    tracks = None

    if clip is not None and hasattr(clip, "tracking"):
        tracks = clip.tracking.tracks
    elif hasattr(clip, "remove") and hasattr(clip, "active"):
        tracks = clip
    
    if tracks is None and hasattr(track, "id_data"):
        parent = track.id_data
        if hasattr(parent, "tracking"):
            tracks = parent.tracking.tracks
            clip = parent

    if tracks is None:
        return

    try:
        op = bpy.ops.clip.track_remove
    except AttributeError:
        op = None

    if op is not None:
        try:
            context = bpy.context
            area = next(
                (a for a in context.screen.areas if a.type == "CLIP_EDITOR"),
                None,
            )
            region = (
                next((r for r in area.regions if r.type == "WINDOW"), None)
                if area
                else None
            )
            if area and region:
                space = area.spaces.active
                if hasattr(track, "select"):
                    track.select = True
                tracks.active = track
                with context.temp_override(
                    area=area, region=region, space_data=space, clip=clip
                ):
                    op()
                # Operator might silently fail to remove the track
                still_there = (
                    track in tracks
                    or (
                        hasattr(tracks, "get") and tracks.get(getattr(track, "name", ""))
                        is not None
                    )
                )
                if still_there and hasattr(tracks, "remove"):
                    tracks.remove(track)
                return
        except Exception:  # pragma: no cover - fallback
            pass

    safe_track = tracks.get(track.name) if hasattr(tracks, "get") else track
    if safe_track and hasattr(tracks, "remove"):
        tracks.remove(safe_track)


def count_markers_in_frame(tracks, frame):
    """Return the number of markers on ``frame`` across ``tracks``.

    Parameters
    ----------
    tracks : iterable
        Collection of tracks containing marker lists.
    frame : int
        The frame for which markers should be counted.

    Returns
    -------
    int
        Number of tracks that have at least one marker on ``frame``.
    """

    count = 0
    for track in tracks:
        try:
            markers = track.markers
        except AttributeError:
            continue
        if any(getattr(m, "frame", None) == frame for m in markers):
            count += 1
    return count
