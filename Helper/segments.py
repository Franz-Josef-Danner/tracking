# Helper/segments.py
def track_has_internal_gaps(track) -> bool:
    frames = sorted([m.frame for m in track.markers])
    if len(frames) < 3:
        return False
    return any(frames[i] - frames[i - 1] > 1 for i in range(1, len(frames)))

def get_track_segments(track):
    frames = sorted([m.frame for m in track.markers])
    if not frames:
        return []
    segments = []
    current = [frames[0]]
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] == 1:
            current.append(frames[i])
        else:
            segments.append(current)
            current = [frames[i]]
    segments.append(current)
    return segments
