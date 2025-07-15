"""Asynchronous feature detection utilities using :mod:`bpy.app.timers`."""

from __future__ import annotations

import bpy

from .detect_no_proxy import detect_features_no_proxy


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

    if logger:
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
        if not ok:
            if logger:
                logger.error("Detection step failed")
            return None
        marker_count = len(clip.tracking.tracks)
        if logger:
            logger.debug(f"Markers detected: {marker_count}")
            logger.debug(
                f"Evaluating: marker_count={marker_count}, "
                f"min_marker_count={getattr(scene, 'min_marker_count', 10)}, "
                f"attempt={state['attempt']}, attempts={attempts}"
            )
        if marker_count >= getattr(scene, "min_marker_count", 10) or state["attempt"] >= attempts:
            if logger:
                logger.info(
                    f"Detection finished after {state['attempt'] + 1} attempts with {marker_count} markers"
                )
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



def delayed_call(callback, delay=0.1):
    """Execute ``callback`` after ``delay`` seconds if a clip is active."""

    def _delayed():
        if not getattr(bpy.context.space_data, "clip", None):
            print("Kein Clip verf\u00fcgbar \u2013 Feature Detection abgebrochen.")
            return None
        callback()
        return None

    bpy.app.timers.register(_delayed, first_interval=delay)


__all__ = ["detect_features_async", "delayed_call"]
