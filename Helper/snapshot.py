import bpy
from dataclasses import dataclass
from typing import List

@dataclass
class MarkerSnapshot:
    frame: int
    co_x: float
    co_y: float
    is_keyed: bool
    mute: bool

    def __repr__(self):
        return f"MarkerSnapshot(frame={self.frame}, co=({self.co_x:.4f},{self.co_y:.4f}), keyed={self.is_keyed}, mute={self.mute})"


def capture_current_frame_markers(context) -> List[MarkerSnapshot]:
    """Erfasst alle aktiven (nicht gemuteten) Tracking Marker des aktuellen Frames.

    Voraussetzung: Ein Movie Clip ist aktiv und hat Tracking-Daten.
    """
    markers_out: List[MarkerSnapshot] = []
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print("[Kaiserlich Tracker] Kein Clip Editor Kontext.")
        return markers_out

    clip = space.clip
    if not clip:
        print("[Kaiserlich Tracker] Kein aktiver Movie Clip.")
        return markers_out

    tracking = clip.tracking
    frame_current = context.scene.frame_current

    # Durch alle Tracks iterieren und Marker des aktuellen Frames sammeln
    for track in tracking.tracks:
        marker = track.markers.find_frame(frame_current)
        if marker is None:
            continue
        if marker.mute:
            continue
        # marker.co sind normalisierte Koordinaten (0..1)
        snap = MarkerSnapshot(
            frame=marker.frame,
            co_x=marker.co[0],
            co_y=marker.co[1],
            is_keyed=marker.is_keyed,
            mute=marker.mute,
        )
        markers_out.append(snap)

    print(f"[Kaiserlich Tracker] Snapshot Frame {frame_current}: {len(markers_out)} Marker")
    for ms in markers_out:
        print("  ", ms)

    return markers_out
