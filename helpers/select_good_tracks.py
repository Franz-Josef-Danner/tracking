import bpy
from .prefix_good import PREFIX_GOOD

def select_good_tracks(clip=None):
    """Selektiert alle Tracks mit dem Präfix GOOD_."""
    if clip is None:
        clip = bpy.context.space_data.clip
    if not clip:
        print("[WARNUNG] Kein Clip aktiv.")
        return

    for track in clip.tracking.tracks:
        track.select = track.name.startswith(PREFIX_GOOD)
