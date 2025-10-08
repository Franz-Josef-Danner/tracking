"""
Marker Positions Helper
=======================

This module provides a utility function for retrieving the 2D positions
of a tracking marker (track) across a range of frames in Blender's
Movie Clip Editor.  The function is designed to work with a single
``MovieTrackingTrack`` and will return up to ``max_frames`` recent
marker positions ending at a specified current frame.

The positions are returned in normalized clip coordinates, matching
Blender's tracking data representation.  Each position is returned
alongside its corresponding frame number.

Usage:

    import bpy
    from .marker_positions_helper import get_positions

    track = bpy.context.space_data.clip.tracking.tracks.active
    cur_frame = bpy.context.scene.frame_current
    positions = get_positions(track, cur_frame, max_frames=5)
    # positions is a list of (frame_number, mathutils.Vector) tuples

References:
    - ``MovieTrackingMarker.co`` property stores the marker position
      for a given frame in normalized coordinates【111914411816643†L2128-L2135】.
    - ``MovieTrackingMarkers.find_frame`` can be used to retrieve the
      marker for a specific frame【706584264448716†L2126-L2143】.
"""

import bpy
import logging

logger = logging.getLogger(__name__)

def get_positions(track: 'bpy.types.MovieTrackingTrack', current_frame: int, max_frames: int = 5):
    """Return up to ``max_frames`` marker positions for a track.

    Parameters
    ----------
    track : bpy.types.MovieTrackingTrack
        The tracking track whose marker positions should be queried.
    current_frame : int
        The frame number to end the sampling on (inclusive).  This is
        typically the current frame in the scene.
    max_frames : int, optional
        The maximum number of frames to sample, by default 5.  If the
        track contains fewer frames preceding ``current_frame``, fewer
        results will be returned.

    Returns
    -------
    list[tuple[int, bpy.types.Vector]]
        A list of tuples ``(frame_number, co)`` where ``co`` is a
        ``mathutils.Vector`` representing the marker's normalized
        coordinates for that frame.  Frames are returned in
        ascending order.  Frames for which no marker exists are
        silently skipped.
    """
    # Access the collection of markers on the track.  This collection
    # provides the ``find_frame`` method which returns a
    # MovieTrackingMarker for an exact frame【706584264448716†L2126-L2143】.
    markers = track.markers
    positions: list[tuple[int, any]] = []

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "get_positions: track=%s current_frame=%s max_frames=%s",
            getattr(track, 'name', '<unnamed>'),
            current_frame,
            max_frames,
        )

    # Determine the earliest frame to inspect.  We walk backwards
    # ``max_frames - 1`` frames from the current frame.
    start_frame = current_frame - (max_frames - 1)

    # Loop from the start frame up to the current frame (inclusive).
    # For each frame we try to find an exact marker.  If none exists,
    # ``find_frame`` returns ``None`` and we skip that frame.
    for frame in range(start_frame, current_frame + 1):
        try:
            marker = markers.find_frame(frame, exact=True)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "get_positions: Fehler beim Zugriff auf Frame %s für Track %s: %s",
                frame,
                getattr(track, 'name', '<unnamed>'),
                exc,
            )
            continue
        if marker is None:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "get_positions: Track %s kein Marker @Frame %s",
                    getattr(track, 'name', '<unnamed>'),
                    frame,
                )
            continue
        positions.append((frame, marker.co.copy()))
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "get_positions: Track %s Marker @Frame %s ko=(%.6f, %.6f)",
                getattr(track, 'name', '<unnamed>'),
                frame,
                marker.co[0],
                marker.co[1],
            )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "get_positions: Track %s gesammelt %d Frames (Start=%s Ende=%s) Frames=%s",
            getattr(track, 'name', '<unnamed>'),
            len(positions),
            start_frame,
            current_frame,
            [f for f, _ in positions],
        )
    return positions
