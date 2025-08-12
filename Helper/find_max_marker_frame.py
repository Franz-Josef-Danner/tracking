import bpy
from typing import Optional, Tuple, Dict

def _get_active_clip_from_context(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Robust: bevorzugt CLIP_EDITOR; fällt auf context.space_data.clip zurück."""
    # 1) Versuche aktiven CLIP_EDITOR zu finden
    screen = getattr(context, "screen", None)
    if screen:
        for a in screen.areas:
            if a.type == 'CLIP_EDITOR':
                sp = a.spaces.active
                clip = getattr(sp, "clip", None)
                if clip:
                    return clip
    # 2) Fallback: aktueller space_data
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    return clip

def _count_active_markers_per_frame(
    clip: bpy.types.MovieClip,
    frame_start: int,
    frame_end: int,
) -> Dict[int, int]:
    """
    Zählt pro Frame alle *aktiven* Marker:
      - Track darf nicht gemutet sein (track.mute == False)
      - Marker darf nicht gemutet sein (marker.mute == False)
    Selektion wird komplett ignoriert.
    """
    counts: Dict[int, int] = {}
    tracks = getattr(clip, "tracking", None).tracks if clip else None
    if not tracks:
        return counts

    for tr in tracks:
        if getattr(tr, "mute", False):
            continue  # inaktiver Track -> ignorieren
        # Snapshot über tr.markers
        for mk in list(tr.markers):
            if getattr(mk, "mute", False):
                continue  # stummgeschalteter Marker -> ignorieren
            f = getattr(mk, "frame", None)
            if f is None or f < frame_start or f > frame_end:
                continue
            counts[f] = counts.get(f, 0) + 1

    return counts

def find_max_active_marker_frame_from_context(
    context: bpy.types.Context,
    *,
    prefer_earliest_on_tie: bool = True,
) -> Optional[Tuple[int, int]]:
    """
    Ermittelt (frame, count) innerhalb scene.frame_start..scene.frame_end.
    Nur *aktive* Marker (Track nicht gemutet, Marker nicht gemutet).
    Selektion wird ignoriert.
    """
    scene = getattr(context, "scene", None)
    if not scene:
        return None
    frame_start = int(scene.frame_start)
    frame_end   = int(scene.frame_end)

    clip = _get_active_clip_from_context(context)
    if not clip:
        return None

    counts = _count_active_markers_per_frame(clip, frame_start, frame_end)
    if not counts:
        return None

    if prefer_earliest_on_tie:
        # Bei Gleichstand gewinnt der kleinere Frame
        frame, cnt = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    else:
        # Alternativ: bei Gleichstand gewinnt der größere Frame
        frame, cnt = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return frame, cnt

def write_max_active_marker_frame_to_scene(
    context: bpy.types.Context,
    *,
    prefer_earliest_on_tie: bool = True,
) -> bool:
    """
    Komfort-Hook: schreibt Ergebnis nach scene["max_marker_frame"] / ["max_marker_count"].
    Rückgabe True bei Erfolg, sonst False.
    """
    res = find_max_active_marker_frame_from_context(context, prefer_earliest_on_tie=prefer_earliest_on_tie)
    if not res:
        return False
    frame, count = res
    scene = context.scene
    scene["max_marker_frame"] = int(frame)
    scene["max_marker_count"] = int(count)
    return True
