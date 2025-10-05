import bpy
from dataclasses import dataclass
from typing import List

@dataclass
class NewTrackSnapshot:
    track_name: str
    frame: int
    co_x: float
    co_y: float

    def __repr__(self):
        return f"NewTrackSnapshot(track={self.track_name}, frame={self.frame}, co=({self.co_x:.4f},{self.co_y:.4f}))"


def capture_new_tracks(context, old_track_names) -> List[NewTrackSnapshot]:
    """Ermittelt neue Tracks (Marker) nach Feature Detection.

    old_track_names: Set oder Liste mit vorhandenen Track-Namen vor detect.
    Gibt Liste neuer Track Snapshots am aktuellen Frame zurück.
    """
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        return []
    clip = space.clip
    if not clip:
        return []
    tracking = clip.tracking
    frame_current = context.scene.frame_current
    old_names = set(old_track_names)
    new_list: List[NewTrackSnapshot] = []
    for track in tracking.tracks:
        if track.name in old_names:
            continue
        # Nur Marker des aktuellen Frames (falls vorhanden)
        marker = track.markers.find_frame(frame_current)
        if marker is None:
            continue
        if marker.mute:
            continue
        new_list.append(NewTrackSnapshot(
            track_name=track.name,
            frame=marker.frame,
            co_x=marker.co[0],
            co_y=marker.co[1],
        ))
    return new_list
