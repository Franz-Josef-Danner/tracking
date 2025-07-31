import bpy


def get_tracking_lengths():
    """Ermittelt für alle selektierten Tracking-Tracks die Tracking-Länge in Frames."""
    space = bpy.context.space_data
    clip = space.clip if space and space.type == 'CLIP_EDITOR' else None

    if not clip:
        print("❌ Kein Clip aktiv oder falscher Editor.")
        return {}

    results = {}
    for track in clip.tracking.tracks:
        if not track.select:
            continue

        valid_frames = sorted([
            marker.frame for marker in track.markers if not marker.mute
        ])

        if valid_frames:
            start = valid_frames[0]
            end = valid_frames[-1]
            length = len(set(valid_frames))
            results[track.name] = {
                "start": start,
                "end": end,
                "length": length,
            }

    return results
