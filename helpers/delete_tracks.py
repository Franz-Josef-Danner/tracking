import bpy

def delete_selected_tracks():
    """Löscht alle selektierten Tracks im aktiven Clip."""
    clip = bpy.context.space_data.clip
    if not clip:
        return

    tracks = clip.tracking.tracks

    # Sammle alle Indizes selektierter Tracks
    indices_to_delete = [i for i, t in enumerate(tracks) if t.select]

    # Rückwärts löschen (sicher bei Index-Änderung)
    for index in reversed(indices_to_delete):
        tracks.remove(tracks[index])
