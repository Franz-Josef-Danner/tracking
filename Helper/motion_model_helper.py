"""
Motion Model Helper
===================

This module contains a function to apply a simple motion model to a
tracking track in Blender.  The motion model consists of a sequence
of target positions (in normalized coordinates) for specific frames
and a desired motion model enum to assign to the track.  Each target
position will overwrite the existing marker position for its frame.

Blender stores tracking data in ``MovieTrackingMarker`` objects.  The
``co`` property of a marker holds the normalized coordinate of the
marker on that frame【111914411816643†L2128-L2135】.  This helper uses the
``find_frame`` method of the track's marker collection to find the
appropriate marker for each frame and updates its ``co`` property.

After updating the positions, the helper sets the track's
``motion_model`` property to one of Blender's supported motion model
enums.  The valid values are ``'Loc'``, ``'LocRot'``, ``'LocScale'``,
``'LocRotScale'``, ``'Affine'`` and ``'Perspective'``【646072811079919†L2217-L2241】.

Usage:

    from .motion_model_helper import apply_motion_model
    # Suppose ``predicted`` is a list of (frame, (x, y)) pairs.
    apply_motion_model(track, predicted, motion_model='Loc')

References:
    - ``MovieTrackingMarkers.find_frame`` documentation【706584264448716†L2126-L2143】.
    - ``MovieTrackingMarker.co`` property【111914411816643†L2128-L2135】.
    - ``MovieTrackingTrack.motion_model`` enumerations【646072811079919†L2217-L2241】.
"""

import bpy

def apply_motion_model(track: 'bpy.types.MovieTrackingTrack',
                       modeled_positions: list[tuple[int, tuple[float, float]]],
                       motion_model: str = 'Loc') -> None:
    """Apply predicted marker positions and set the track's motion model.

    Parameters
    ----------
    track : bpy.types.MovieTrackingTrack
        The tracking track whose marker positions should be updated.
    modeled_positions : list[tuple[int, tuple[float, float]]]
        A list of tuples ``(frame_number, (x, y))`` where ``x`` and
        ``y`` are the normalized coordinates to assign to the marker at
        that frame.  Frames for which no marker exists will be skipped.
    motion_model : str, optional
        The motion model to assign to the track after updating the
        markers.  Must be one of Blender's supported motion model
        values (e.g. ``'Loc'``, ``'LocRot'``, etc.).  Defaults to
        ``'Loc'``.

    Notes
    -----
    - This helper does not create new markers.  It only updates
      existing markers.  If a frame in ``modeled_positions`` has no
      corresponding marker, that entry is ignored.
    - The coordinates provided must already be in normalized clip
      space.  They are assigned directly to ``marker.co``.
    - After applying the positions, the track's ``motion_model``
      property is set to the given value【646072811079919†L2217-L2241】.
    """
    markers = track.markers
    for frame, coords in modeled_positions:
        marker = markers.find_frame(frame, exact=True)
        if marker is None:
            # If there is no marker for this frame we skip updating it.
            continue
        x, y = coords
        # Assign new normalized coordinates.  ``co`` expects a 2D vector
        # of floats【111914411816643†L2128-L2135】.
        marker.co = (x, y)

    # Update the track's motion model.  Blender will clamp invalid
    # values to the allowed enumeration set【646072811079919†L2217-L2241】.
    track.motion_model = motion_model
