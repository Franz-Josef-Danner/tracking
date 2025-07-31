import bpy

def delete_selected_tracks():
    """Delete all selected tracks from the active movie clip."""
    clip = bpy.context.space_data.clip
    if not clip:
        print("No active Movie Clip in context!")
        return
    tracks = clip.tracking.tracks
    # Copy selected tracks to a separate list for safe iteration
    selected_tracks = [t for t in tracks if t.select]
    for track in selected_tracks:
        tracks.remove(track)
    print(f"Deleted {len(selected_tracks)} tracks.")
