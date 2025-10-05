import bpy

def run(track):
    """Löscht einen gegebenen Track aus seinem Clip."""
    try:
        clip = bpy.context.edit_movieclip
        if not clip:
            print('delete: kein Clip aktiv')
            return False
        clip.tracking.tracks.remove(track)
        print(f'delete: Track {track.name} entfernt')
        return True
    except Exception as e:
        print(f'delete: Fehler {e}')
        return False