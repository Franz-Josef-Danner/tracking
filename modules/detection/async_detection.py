"""Asynchronous feature detection utilities using :mod:`bpy.app.timers`."""

from __future__ import annotations

import bpy

from .detect_no_proxy import detect_features_no_proxy
from .distance_remove import distance_remove
from ..util.tracking_utils import hard_remove_new_tracks, safe_remove_track
from ..util.tracker_logger import TrackerLogger


def detect_features_async(scene, clip, logger=None, attempts=10):
    """Detect features asynchronously via :mod:`bpy.app.timers`.

    Parameters
    ----------
    scene : :class:`bpy.types.Scene`
        Scene containing detection settings like ``min_marker_count``.
    clip : :class:`bpy.types.MovieClip`
        Movie clip on which features should be detected.
    logger : :class:`TrackerLogger`, optional
        Logger for debug output.
    attempts : int, optional
        Maximum number of detection attempts. Defaults to 10.
    """

    settings = clip.tracking.settings
    state = {
        "attempt": 0,
        "threshold": 1.0,
        "pattern_size": getattr(settings, "default_pattern_size", 11),
        "expected": getattr(scene, "min_marker_count", 10) * 4,
    }

    if hasattr(scene, "kaiserlich_feature_detection_done"):
        scene.kaiserlich_feature_detection_done = False

    if logger is None:
        logger = TrackerLogger()
    logger.debug(
        f"Starting async detection: attempts={attempts}, expected={state['expected']}, "
        f"pattern_size={state['pattern_size']}"
    )

    def _step():
        if logger:
            logger.debug(
                f"Attempt {state['attempt'] + 1}: threshold={state['threshold']}, pattern_size={state['pattern_size']}"
            )
        ok = detect_features_no_proxy(
            clip,
            threshold=state["threshold"],
            margin=clip.size[0] / 200,
            min_distance=int(clip.size[0] / 20),
            logger=logger,
        )
        if logger:
            logger.debug(f"Detection call returned {ok}")
        if not ok:
            if logger:
                logger.error("Detection step failed")
            return None
        # rename newly detected tracks
        existing_names = {t.name for t in clip.tracking.tracks}
        idx = 0
        for track in clip.tracking.tracks:
            if track.name.startswith(("Track", "Track.", "Track_")):
                new_name = f"NEW_{idx:03}"
                while new_name in existing_names:
                    idx += 1
                    new_name = f"NEW_{idx:03}"
                track.name = new_name
                existing_names.add(new_name)
                idx += 1

        # remove NEW_ tracks close to GOOD_ markers
        good_tracks = [t for t in clip.tracking.tracks if t.name.startswith("GOOD_")]
        new_tracks = [t for t in clip.tracking.tracks if t.name.startswith("NEW_")]
        if logger:
            logger.debug(f"Found {len(good_tracks)} GOOD_ tracks for filtering")
            logger.debug(f"Found {len(new_tracks)} NEW_ tracks before distance filtering")
        if not good_tracks and logger:
            logger.warning("No GOOD_ tracks found – skipping proximity filtering")
        margin_dist = int(clip.size[0] / 20)
        for good in good_tracks:
            try:
                pos = good.markers[0].co
            except (AttributeError, IndexError):
                continue
            distance_remove(clip.tracking.tracks, pos, margin_dist, logger=logger)

        if logger:
            logger.debug("Starting marker count check")
        marker_count = len([t for t in clip.tracking.tracks if t.name.startswith("NEW_")])
        min_marker_count = getattr(scene, "min_marker_count", 10)
        min_plus = min_marker_count * 4
        min_valid = min_plus * 0.8
        max_valid = min_plus * 1.2
        if logger:
            logger.debug(f"Markers detected: {marker_count}")
            logger.debug(
                f"Evaluating: marker_count={marker_count}, min_marker_count={min_marker_count}, "
                f"min_valid={min_valid}, max_valid={max_valid}, attempt={state['attempt']}, attempts={attempts}"
            )
        if (min_valid <= marker_count <= max_valid) or state["attempt"] >= attempts:
            if logger:
                logger.info(
                    f"Detection finished after {state['attempt'] + 1} attempts with {marker_count} markers"
                )
            for track in clip.tracking.tracks:
                if track.name.startswith("NEW_"):
                    track.name = track.name.replace("NEW_", "TRACK_")
            if hasattr(scene, "kaiserlich_feature_detection_done"):
                scene.kaiserlich_feature_detection_done = True
            return None
        if logger:
            logger.debug("Removing existing tracks before retrying")
        hard_remove_new_tracks(clip, logger=logger)
        remaining = len([t for t in clip.tracking.tracks if t.name.startswith("NEW_")])
        if logger:
            logger.debug(f"Remaining NEW_ tracks after removal: {remaining}")
        if remaining:
            if logger:
                logger.warning(f"{remaining} NEW_ tracks could not be removed")
            return None
        new_threshold = max(
            round(state["threshold"] * ((marker_count + 0.1) / state["expected"]), 5),
            0.0001,
        )
        if logger and new_threshold != state["threshold"]:
            logger.debug(f"Adjusting threshold to {new_threshold}")
        state["threshold"] = new_threshold
        if state["pattern_size"] < 100:
            state["pattern_size"] = min(int(state["pattern_size"] * 1.1), 100)
            settings.default_pattern_size = state["pattern_size"]
            if logger:
                logger.debug(f"Pattern size adjusted to {state['pattern_size']}")
        state["attempt"] += 1
        return 0.1

    bpy.app.timers.register(_step)
    if logger:
        logger.debug("Async detection timer registered")



def delayed_call(callback, delay=0.1, logger=None):
    """Execute ``callback`` after ``delay`` seconds if a clip is active."""

    def _delayed():
        if not getattr(bpy.context.space_data, "clip", None):
            if logger is None:
                TrackerLogger().warning(
                    "Kein Clip verf\u00fcgbar \u2013 Feature Detection abgebrochen."
                )
            else:
                logger.warning(
                    "Kein Clip verf\u00fcgbar \u2013 Feature Detection abgebrochen."
                )
            return None
        callback()
        return None

    bpy.app.timers.register(_delayed, first_interval=delay)


__all__ = ["detect_features_async", "delayed_call"]
