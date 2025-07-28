import bpy
from .prefix_new import PREFIX_NEW

def select_new_tracks(clip=None):
    """Selektiert alle Tracks mit dem Präfix NEW_."""
    if clip is None:
        clip = bpy.context.space_data.clip
    if not clip:
        print("[WARNUNG] Kein Clip aktiv.")
        return

    for track in clip.tracking.tracks:
        track.select = track.name.startswith(PREFIX_NEW)
