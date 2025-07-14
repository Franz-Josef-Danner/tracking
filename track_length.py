"""Utility to remove short tracks."""


def remove_short_tracks(clip, min_length):
    for track in list(clip.tracking.tracks):
        frames = [m.frame for m in track.markers]
        if frames and max(frames) - min(frames) < min_length:
            clip.tracking.tracks.remove(track)
