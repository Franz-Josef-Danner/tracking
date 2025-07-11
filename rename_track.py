"""Prefix tracks with TRACK_."""

import bpy

from rename_new import PREFIXES, rename_tracks as _rename


def rename_tracks(marker_infos, prefix="TRACK_"):
    """Rename tracks to start with TRACK_."""
    _rename(marker_infos, prefix)
