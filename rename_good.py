"""Prefix tracks with GOOD_."""

from rename_new import rename_tracks as _rename


def rename_tracks(marker_infos, prefix="GOOD_"):
    """Rename tracks to start with GOOD_."""
    _rename(marker_infos, prefix)
