"""Utility helpers for Blender tracking."""

from __future__ import annotations

import bpy


def _track_exists(tracks, track):
    """Return ``True`` if ``track`` is present in ``tracks``."""
    try:
        if track in tracks:
            return True
    except TypeError:
        pass

    name = getattr(track, "name", None)
    if name is None:
        return False

    try:
        if name in tracks:
            return True
    except TypeError:
        pass

    if hasattr(tracks, "get"):
        return tracks.get(name) is not None

    return any(getattr(t, "name", None) == name for t in tracks)


def safe_remove_track(clip, track, logger=None):
    """Safely remove ``track`` from ``clip``.

    Tries to call :func:`bpy.ops.clip.track_remove` in a Clip Editor UI
    context. If the operator cannot be executed, falls back to directly
    removing the track from ``clip.tracking.tracks``. Returns ``True`` when
    the track no longer exists after the attempt, otherwise ``False``.
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
        return False

    try:
        op = bpy.ops.clip.track_remove
    except AttributeError:
        op = None

    op_success = False
    clip_editor_found = False
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
                clip_editor_found = True
                space = area.spaces.active
                if hasattr(track, "select"):
                    track.select = True
                tracks.active = track
                with context.temp_override(
                    area=area, region=region, space_data=space, clip=clip
                ):
                    result = op()
                op_success = result == {"FINISHED"}
        except Exception:  # pragma: no cover - fallback
            pass
    if op is not None and not clip_editor_found and logger:
        logger.warning("No CLIP_EDITOR area found; falling back to direct removal")

    still_there = _track_exists(tracks, track)
    if still_there and hasattr(tracks, "remove"):
        try:
            tracks.remove(track)
            op_success = True
        except Exception as exc:  # pragma: no cover - fallback
            if logger:
                logger.warning(f"Track remove fallback failed for {track.name}: {exc}")

    still_there = _track_exists(tracks, track)
    if still_there and logger:
        logger.warning(f"Track '{track.name}' still exists after attempted removal!")
    return not still_there


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
