import bpy
from delet import delete_track_by_name_index


def check_new_marker_count(min_count_plus_min: int, min_count_plus_max: int) -> int:
    """Check NEW_ marker count and remove them if out of range.

    Parameters
    ----------
    min_count_plus_min: int
        Lower bound for expected NEW_ marker count.
    min_count_plus_max: int
        Upper bound for expected NEW_ marker count.

    Returns
    -------
    int
        Number of NEW_ markers found before any deletion.
    """
    clip = bpy.context.space_data.clip
    if not clip:
        print("[count_new_markers] No active clip found.")
        return 0

    tracks = clip.tracking.tracks
    new_tracks = [t for t in tracks if t.name.startswith("NEW_")]
    new_count = len(new_tracks)
    print(f"[count_new_markers] Found {new_count} NEW_ markers.")

    if new_count <= min_count_plus_min or new_count >= min_count_plus_max:
        print(
            "[count_new_markers] Count outside expected range - deleting NEW_ markers."
        )
        for t in new_tracks:
            idx = tracks.find(t.name)
            delete_track_by_name_index(t.name, idx)
    else:
        print("[count_new_markers] Count within expected range.")

    return new_count


__all__ = ["check_new_marker_count"]
