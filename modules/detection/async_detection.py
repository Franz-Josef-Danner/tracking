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

     def _step():
         detect_features_no_proxy(
             clip,
             threshold=state["threshold"],
             margin=clip.size[0] / 200,
             distance=clip.size[0] / 20,
             logger=logger,
         )
         marker_count = len(clip.tracking.tracks)
         if marker_count >= getattr(scene, "min_marker_count", 10) or state["attempt"] >= attempts:
             return None
         state["threshold"] = max(
             round(state["threshold"] * ((marker_count + 0.1) / state["expected"]), 5),
             0.0001,
         )
         if state["pattern_size"] < 100:
             state["pattern_size"] = min(int(state["pattern_size"] * 1.1), 100)
             settings.default_pattern_size = state["pattern_size"]
             if logger:
                 logger.debug(f"Pattern size adjusted to {state['pattern_size']}")
         state["attempt"] += 1
         return 0.1

     bpy.app.timers.register(_step)


__all__ = ["detect_features_async"]
