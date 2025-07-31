import bpy

def delete_selected_tracks():
    clip = bpy.context.space_data.clip
    if not clip:
        print("❌ Kein Clip im aktuellen Kontext")
        return

    tracks_to_delete = [t for t in clip.tracking.tracks if t.select]
    print(f"➤ {len(tracks_to_delete)} Marker werden gelöscht...")

    for track in tracks_to_delete:
        clip.tracking.tracks.remove(track)
