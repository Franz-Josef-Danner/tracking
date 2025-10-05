import bpy
from . import snapshot

def run(context):
    """Vergleicht aktuelle Track-Liste mit Snapshot und klassifiziert Marker.

    AMA = alter Marker
    NM  = neuer Marker
    """
    clip = bpy.context.edit_movieclip
    if not clip:
        print('compare: kein Clip')
        return
    prev = snapshot.get_previous_for_clip(clip)
    current_tracks = list(clip.tracking.tracks)
    if not prev:
        print('compare: kein vorheriger Snapshot – alle Marker als NM')
    for t in current_tracks:
        label = 'AMA' if t.name in prev else 'NM'
        print(f'compare: {label} {t.name}')
    # Optional könnte man neue Marker markieren / umbenennen.