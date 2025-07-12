"""Helpers for counting and validating NEW_ markers."""

import bpy
import logging

logger = logging.getLogger(__name__)


def count_new_markers(context, clip, prefix="NEW_"):
    """Return and store the number of tracks starting with ``prefix``."""

    new_count = sum(1 for t in clip.tracking.tracks if t.name.startswith(prefix))
    context.scene.new_marker_count = new_count
    return new_count


