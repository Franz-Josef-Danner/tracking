import bpy

def delete_selected_tracks():
    """Löscht alle selektierten Tracks im aktiven Clip."""
    clip = bpy.context.space_data.clip
    if not clip:
        print("❌ Kein aktiver Movie Clip im Kontext!")
        return

    tracks = clip.tracking.tracks
    selected_tracks = [t for t in tracks if t.select]

    print(f"➤ {len(selected_tracks)} Marker werden gelöscht...")

    for track in selected_tracks:
        try:
            tracks.remove(track)
            print(f"  🗑️ Track '{track.name}' gelöscht.")
        except Exception as e:
            print(f"  ⚠️ Fehler beim Löschen von '{track.name}': {e}")
