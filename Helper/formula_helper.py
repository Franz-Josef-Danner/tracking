"""
Formula Helper
==============

This module defines a function that orchestrates the process of
sampling recent marker positions, fitting a simple linear motion
formula to the sampled data, and then applying the resulting motion
model back onto the track.  The helper works on all selected
tracking tracks (or the active track if no tracks are selected) in
Blender's Movie Clip Editor.  It is designed to be invoked from a
custom operator that performs frame-by-frame tracking, providing a
hook for post-processing each frame.

The motion model in this context is a straight-line fit through the
latest 1–5 sampled marker positions.  A least-squares linear
regression is performed independently on the x and y coordinates as
functions of the frame number.  The fitted model is then evaluated
exactly on the sampled frames to obtain smoothed positions.  Finally,
the updated positions are written back to the track and the track's
``motion_model`` property is set to ``'Loc'`` (translation only).

This approach can reduce jitter in tracking data by enforcing a
consistent translational motion across several frames.

Usage:

    from .formula_helper import apply_formula_on_selected_tracks
    apply_formula_on_selected_tracks(bpy.context, max_frames=5)

References:
    - ``MovieTrackingMarker.co`` property【111914411816643†L2128-L2135】.
    - ``MovieTrackingMarkers.find_frame`` for marker retrieval【706584264448716†L2126-L2143】.
    - ``MovieTrackingTrack.motion_model`` enumerations【646072811079919†L2217-L2241】.
    - ``MovieTrackingTrack.select`` property indicates whether a track is selected【646072811079919†L2272-L2278】.
"""

from __future__ import annotations

import bpy
import logging
from typing import List, Tuple

from .marker_positions_helper import get_positions
from .motion_model_helper import apply_motion_model

# Modul-Logger
logger = logging.getLogger(__name__)


def _linear_regression(frames: List[int], values: List[float]) -> Tuple[float, float]:
    """Compute slope and intercept for a simple linear regression.

    Parameters
    ----------
    frames : List[int]
        The independent variable values (frame numbers).
    values : List[float]
        The dependent variable values (x or y coordinates).

    Returns
    -------
    Tuple[float, float]
        A tuple ``(intercept, slope)`` representing the parameters of
        the fitted line ``value = intercept + slope * frame``.
    """
    n = len(frames)
    if n == 0:
        return 0.0, 0.0
    f_avg = sum(frames) / n
    v_avg = sum(values) / n
    denom = sum((f - f_avg) ** 2 for f in frames)
    # Avoid division by zero; if all frames are identical, slope = 0.
    if denom == 0.0:
        return v_avg, 0.0
    slope = sum((f - f_avg) * (v - v_avg) for f, v in zip(frames, values)) / denom
    intercept = v_avg - slope * f_avg
    return intercept, slope


def apply_formula_on_selected_tracks(context: bpy.types.Context, max_frames: int = 5) -> None:
    """Sample, fit and apply a linear motion model to selected tracks.

    This function retrieves up to ``max_frames`` recent marker positions
    for each selected track (or the active track if none are selected),
    computes a linear least‑squares fit on the x and y coordinates
    separately, and then updates the markers with the fitted positions.
    Finally, it sets the track's ``motion_model`` property to ``'Loc'``.

    Parameters
    ----------
    context : bpy.types.Context
        The Blender context from which to obtain the current scene and
        clip.  It is assumed that the operator invoking this helper
        runs in the Movie Clip Editor, so ``context.space_data.clip``
        will reference the active clip.
    max_frames : int, optional
        The maximum number of frames to consider when fitting the
        motion model.  Defaults to 5.  If fewer than ``max_frames``
        markers exist before the current frame, all available markers
        are used.

    Notes
    -----
    - If a track contains fewer than two sampled positions, it will be
      skipped because a meaningful line cannot be fitted.
    - The fitted positions are only written back to the sampled
      frames, not extrapolated beyond the sample window.
    - The motion model assigned is always ``'Loc'``, reflecting that
      only translation is being enforced by the fit.
    """
    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        logger.warning("apply_formula_on_selected_tracks: Kein Clip im Kontext vorhanden – Abbruch.")
        return

    # Determine which tracks to process: all selected tracks, or the
    # active track if none are selected.  ``track.select`` is True
    # when the track is selected in the UI【646072811079919†L2272-L2278】.
    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        active_track = clip.tracking.tracks.active
        if active_track:
            selected_tracks = [active_track]

    current_frame = scene.frame_current

    if not selected_tracks:
        logger.info("Keine Tracks ausgewählt oder aktiv – nichts zu tun.")
        return

    logger.debug(
        "apply_formula_on_selected_tracks: frame=%s, max_frames=%s, tracks=%s",
        current_frame,
        max_frames,
        [t.name for t in selected_tracks],
    )

    for track in selected_tracks:
        # Retrieve the marker positions for the most recent frames.
        positions = get_positions(track, current_frame, max_frames=max_frames)
        if len(positions) < 2:
            logger.debug(
                "Track '%s': weniger als zwei Positionen (%d) – übersprungen.",
                track.name,
                len(positions),
            )
            continue

        frames: List[int] = [frame for frame, _co in positions]
        xs: List[float] = [co[0] for _, co in positions]
        ys: List[float] = [co[1] for _, co in positions]

        logger.debug(
            "Track '%s': gesampelte Frames=%s, xs=%s, ys=%s",
            track.name,
            frames,
            [f"{x:.6f}" for x in xs],
            [f"{y:.6f}" for y in ys],
        )

        # Fit linear models to x and y coordinates separately.
        intercept_x, slope_x = _linear_regression(frames, xs)
        intercept_y, slope_y = _linear_regression(frames, ys)

        logger.debug(
            "Track '%s': Regression -> ix=%.6f, sx=%.6f, iy=%.6f, sy=%.6f",
            track.name,
            intercept_x,
            slope_x,
            intercept_y,
            slope_y,
        )

        modeled_positions: list[tuple[int, tuple[float, float]]] = []
        for f in frames:
            x_pred = intercept_x + slope_x * f
            y_pred = intercept_y + slope_y * f
            modeled_positions.append((f, (x_pred, y_pred)))

        logger.debug(
            "Track '%s': modellierte Positionen=%s",
            track.name,
            [
                (f, (f"{co[0]:.6f}", f"{co[1]:.6f}"))
                for f, co in modeled_positions
            ],
        )

        # Apply the smoothed positions and set the track's motion model
        # to 'Loc' (translation only)【646072811079919†L2217-L2241】.
        try:
            apply_motion_model(track, modeled_positions, motion_model='Loc')
            logger.debug("Track '%s': motion_model auf 'Loc' gesetzt und Werte angewendet.", track.name)
        except Exception as exc:  # noqa: BLE001 – wir wollen robust loggen
            logger.error(
                "Track '%s': Fehler beim Anwenden des Motion Models: %s",
                track.name,
                exc,
            )
