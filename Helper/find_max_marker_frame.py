# Helper/find_max_marker_frame.py

import bpy
from typing import List, Tuple

def get_active_marker_counts_sorted(
    context: bpy.types.Context
) -> List[Tuple[int, int]]:
    """
    Liefert (frame, count) für scene.frame_start..scene.frame_end,
    sortiert absteigend nach aktiven Markern.
    Aktiv = marker.mute == False (Selektion ignoriert).
    """
    scene = context.scene
    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)

    # Clip robust holen
    clip = None
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        clip = space.clip
    else:
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                sp = area.spaces.active
                if getattr(sp, "clip", None):
                    clip = sp.clip
                    break
    if not clip:
        return []

    counts = {}
    for tr in clip.tracking.tracks:
        # Kein tr.mute in Blender 4.4 -> nur Marker-Mute werten
        for mk in tr.markers:
            if getattr(mk, "mute", False):
                continue
            f = getattr(mk, "frame", None)
            if f is None or f < frame_start or f > frame_end:
                continue
            counts[f] = counts.get(f, 0) + 1

    # Sortierung: count desc, frame asc (Ties → früherer Frame gewinnt)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
