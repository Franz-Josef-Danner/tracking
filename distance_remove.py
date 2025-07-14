"""Remove tracks that are close to given reference tracks."""

import math


def _distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def remove_nearby_tracks(clip, good_tracks, margin):
    """Delete tracks close to any track in good_tracks."""
    tracks = list(clip.tracking.tracks)
    for track in tracks:
        for good in good_tracks:
            if _distance(track.markers[0].co, good.markers[0].co) < margin:
                clip.tracking.tracks.remove(track)
                break
