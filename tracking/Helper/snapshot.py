"""Snapshot der aktuell aktiven Marker im Frame des Playheads.

Ermittelt alle Marker (Track-Markierungen), deren Frame dem aktuellen Scene-Frame
entspricht und die nicht stummgeschaltet (mute=False) sind.

Rückgabe: Liste von Dictionaries mit: name, frame, co (Tuple[float,float])
"""

import bpy

def _find_marker_for_frame(track, frame):
    # Versucht zuerst die (falls vorhandene) Optimierungs-API
    markers = track.markers
    # Einige Blender Versionen besitzen markers.find_frame
    find_fn = getattr(markers, 'find_frame', None)
    if callable(find_fn):
        try:
            mk = find_fn(frame)
            if mk:
                return mk
        except Exception:
            pass
    # Fallback: lineare Suche
    for mk in markers:
        if mk.frame == frame:
            return mk
    return None


def run(context):
    clip = bpy.context.edit_movieclip
    if not clip:
        print('[snapshot] Kein aktiver Movie Clip gefunden.')
        return []

    frame = context.scene.frame_current
    tracking = clip.tracking
    tracks = tracking.tracks

    lm = []  # Liste der Marker (erfasste Einträge)
    for track in tracks:
        mk = _find_marker_for_frame(track, frame)
        if not mk:
            continue
        if getattr(mk, 'mute', False):
            continue
        co = tuple(mk.co) if hasattr(mk, 'co') else (0.0, 0.0)
        lm.append({
            'track': track.name,
            'frame': mk.frame,
            'co': co,
            'is_keyed': getattr(mk, 'is_keyed', False),
        })

    print(f'[snapshot] Frame {frame}: {len(lm)} Marker gefunden.')
    for entry in lm:
        print(f"  - {entry['track']} @ {entry['frame']} co={entry['co']} keyed={entry['is_keyed']}")

    return lm

__all__ = ['run']