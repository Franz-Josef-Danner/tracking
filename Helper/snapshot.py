import bpy
from typing import List, Dict, Any

# Datentyp für einen einfachen Marker-Snapshot
MarkerSnapshot = Dict[str, Any]

def snapshot_active_markers(context) -> List[MarkerSnapshot]:
    """Erfasst alle aktiven (nicht gemuteten) Marker im aktuellen Frame.
    Gibt eine Liste aus Dictionaries zurück: { 'track': str, 'frame': int, 'co': (x, y), 'is_keyed': bool }
    """
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        print("[Kaiserlich Tracker] snapshot: Kein Clip aktiv.")
        return []

    tracking = getattr(clip, 'tracking', None)
    if tracking is None:
        print("[Kaiserlich Tracker] snapshot: Kein tracking-Objekt.")
        return []

    current_frame = context.scene.frame_current
    result: List[MarkerSnapshot] = []

    for track in tracking.tracks:
        marker = track.markers.find_frame(current_frame)
        if marker is None:
            continue
        if marker.mute:
            continue
        result.append({
            'track': track.name,
            'frame': marker.frame,
            'co': (marker.co[0], marker.co[1]),
            'is_keyed': marker.is_keyed,
        })

    print(f"[Kaiserlich Tracker] snapshot: {len(result)} aktive Marker im Frame {current_frame} erfasst.")
    return result
