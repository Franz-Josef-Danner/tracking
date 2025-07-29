import bpy
from .prefix_new import PREFIX_NEW

def select_new_tracks(clip=None):
    """Select all tracks starting with ``NEW_``.

    Used by :class:`~operators.tracking.cleanup.CLIP_OT_select_new_tracks`.
    """
    if clip is None:
        clip = bpy.context.space_data.clip
    if not clip:
        print("[WARNUNG] Kein Clip aktiv.")
        return

    for track in clip.tracking.tracks:
        track.select = track.name.startswith(PREFIX_NEW)
