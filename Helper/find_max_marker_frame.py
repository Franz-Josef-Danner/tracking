import bpy
from typing import List, Tuple

def get_active_marker_counts_sorted(
    context: bpy.types.Context
) -> List[Tuple[int, int]]:
    """
    Gibt eine Liste (frame, count) für alle Frames zwischen scene.frame_start
    und scene.frame_end zurück, sortiert absteigend nach Anzahl aktiver Marker.
    
    Aktiv = Track.mute == False und Marker.mute == False
    Selektion wird ignoriert.
    """
    scene = context.scene
    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)

    # Clip holen (robust)
    clip = None
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        clip = space.clip
    else:
        # Suche aktiven CLIP_EDITOR
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
        if tr.mute:
            continue
        for mk in tr.markers:
            if mk.mute:
                continue
            f = mk.frame
            if frame_start <= f <= frame_end:
                counts[f] = counts.get(f, 0) + 1

    # Sortierung: erst nach count (absteigend), dann frame (aufsteigend)
    sorted_counts = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return sorted_counts
