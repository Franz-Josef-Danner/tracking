import bpy

def delete_selected_tracks():
    """Löscht alle selektierten Tracks im aktiven Clip."""
    clip = bpy.context.space_data.clip
    if not clip:
        print("⚠ Kein aktiver Clip.")
        return

    tracks = clip.tracking.tracks
    to_delete = [track for track in tracks if track.select]
    print(f"➤ {len(to_delete)} Marker werden gelöscht...")

    for track in to_delete:
        tracks.remove(track)
