"""Prefix tracks with TRACK_."""

from rename_new import rename_tracks as _rename


def rename_tracks(marker_infos, prefix="TRACK_"):
    """Rename tracks to start with TRACK_."""
    _rename(marker_infos, prefix)
