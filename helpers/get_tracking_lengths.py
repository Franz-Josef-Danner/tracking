
def get_tracking_lengths(clip):
    """Return a list with the length of each track in frames."""
    lengths = []
    for track in clip.tracking.tracks:
        frames = [m.frame for m in track.markers if not m.mute and m.co.length_squared != 0.0]
        if frames:
            lengths.append(max(frames) - min(frames) + 1)
    return lengths
