import bpy
from . import snapshot

def run(context):
    """Vergleicht aktuelle Track-Liste mit Snapshot und klassifiziert Marker.

    Rückgabe:
      dict mit Keys:
        new_tracks  -> Liste Track-Objekte, die vorher nicht existierten
        old_tracks  -> Liste Track-Objekte, die bereits existierten
        new_names   -> Set der neuen Track-Namen
        old_names   -> Set der alten Track-Namen
        new_count   -> Anzahl neuer Tracks
        old_count   -> Anzahl alter Tracks

    AMA = Alter Marker (Track existierte im Snapshot)
    NM  = Neuer Marker (Track ist neu seit Snapshot)
    """
    clip = bpy.context.edit_movieclip
    if not clip:
        print('compare: kein Clip')
        return {
            'new_tracks': [], 'old_tracks': [], 'new_names': set(), 'old_names': set(),
            'new_count': 0, 'old_count': 0
        }
    prev = snapshot.get_previous_for_clip(clip)
    prev_counts = snapshot.get_previous_marker_counts(clip)
    current_tracks = list(clip.tracking.tracks)
    if not prev:
        print('compare: kein vorheriger Snapshot – alle Marker als NM')
    new_tracks = []
    old_tracks = []
    for t in current_tracks:
        is_old = t.name in prev
        label = 'AMA' if is_old else 'NM'
        try:
            current_count = len(t.markers)
        except Exception:
            current_count = -1
        old_count = prev_counts.get(t.name, '-')
        print(f'compare: {label} {t.name} markers_now={current_count} markers_prev={old_count}')
        if is_old:
            old_tracks.append(t)
        else:
            new_tracks.append(t)
    result = {
        'new_tracks': new_tracks,
        'old_tracks': old_tracks,
        'new_names': {t.name for t in new_tracks},
        'old_names': {t.name for t in old_tracks},
        'new_count': len(new_tracks),
        'old_count': len(old_tracks),
    }
    print(f"compare: Zusammenfassung -> new={result['new_count']} old={result['old_count']}")
    return result