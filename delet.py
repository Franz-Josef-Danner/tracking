import bpy


def delete_track_by_name_index(name: str, index: int) -> bool:
    """Delete the tracking track with the given ``name`` at ``index``.

    Parameters
    ----------
    name: str
        Name of the track to remove.
    index: int
        Expected index of the track in the tracking list.

    Returns
    -------
    bool
        ``True`` if the track was removed, ``False`` otherwise.
    """
    clip = bpy.context.space_data.clip
    if not clip:
        print("[delet] No active clip found.")
        return False

    tracks = clip.tracking.tracks
    track = tracks.get(name)
    if not track:
        print(f"[delet] Track '{name}' not found.")
        return False

    track_idx = tracks.find(track.name)
    if track_idx != index:
        print(
            f"[delet] Track index mismatch: expected {index}, actual {track_idx}."
        )

    tracks.remove(track)
    print(f"[delet] Removed track '{name}' at index {track_idx}.")
    return True


__all__ = ["delete_track_by_name_index"]
