import bpy
from .prefix_track import PREFIX_TRACK

def select_track_tracks(clip=None):
    """Selektiert alle Tracks mit dem Präfix TRACK_."""
    if clip is None:
        clip = bpy.context.space_data.clip
    if not clip:
        print("[WARNUNG] Kein Clip aktiv.")
        return

    for track in clip.tracking.tracks:
        track.select = track.name.startswith(PREFIX_TRACK)
