"""Add NEW_ prefix to given tracking tracks."""

import bpy

PREFIXES = ("NEW_", "TRACK_", "GOOD_")


def rename_tracks(marker_infos, prefix="NEW_"):
    """Rename tracks so their name starts with ``prefix``.

    ``marker_infos`` should be an iterable of :class:`bpy.types.MovieTrackingTrack`.
    Existing prefixes NEW_, TRACK_ or GOOD_ are stripped before applying
    the new prefix.
    """
    for track in marker_infos:
        name = track.name
        for pre in PREFIXES:
            if name.startswith(pre):
                name = name[len(pre):]
                break
        track.name = f"{prefix}{name}"
