import bpy

# Speichert vorherige Track-Namen je Clip (clip.name -> set(names))
_previous_tracks = {}

def run(context, values: dict):
    """Snapshot der vorhandenen Track-Namen vor der Detection.

    Legt im Modul ein Set der aktuellen Track-Namen ab, damit später verglichen
    werden kann, welche neu sind.
    """
    clip = bpy.context.edit_movieclip
    if not clip:
        print('snapshot: kein Clip')
        return
    frame = context.scene.frame_current
    names = {t.name for t in clip.tracking.tracks}
    _previous_tracks[clip.name] = names
    print(f'snapshot: Frame {frame} Clip {clip.name} gespeicherte Marker: {len(names)}')

def get_previous_for_clip(clip):
    return _previous_tracks.get(clip.name, set())