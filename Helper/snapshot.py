import bpy

# Speichert vorherige Track-Namen je Clip (clip.name -> set(names))
_previous_tracks = {}
_previous_marker_counts = {}

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
    names = {t.name for t in clip.tracking.tracks if not (t.name.startswith('DELETED_') or t.name.startswith('FAILED_DEL_') or t.name.startswith('DELETED_UNREM_'))}
    _previous_tracks[clip.name] = names
    # Markeranzahl je Track erfassen (Frame Count)
    counts = {}
    for t in clip.tracking.tracks:
        try:
            counts[t.name] = len(t.markers)
        except Exception:
            counts[t.name] = -1
    _previous_marker_counts[clip.name] = counts
    print(f'snapshot: Frame {frame} Clip {clip.name} gespeicherte Marker: {len(names)} (Detail counts: {counts})')

def get_previous_for_clip(clip):
    return _previous_tracks.get(clip.name, set())

def get_previous_marker_counts(clip):
    return _previous_marker_counts.get(clip.name, {})