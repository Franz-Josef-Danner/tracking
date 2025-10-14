import bpy
from typing import Iterable, List

def _get_tracking(context):
    clip = context.space_data.clip if getattr(context, "space_data", None) else None
    if clip is None:
        return None
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return None
    return tracking

def _find_clip_editor_area(clip):
    """Sucht eine passende CLIP_EDITOR Area für Context Override."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'CLIP_EDITOR':
                for space in area.spaces:
                    if space.type == 'CLIP_EDITOR':
                        if getattr(space, 'clip', None) == clip or space.clip is None:
                            region_window = None
                            for region in area.regions:
                                if region.type == 'WINDOW':
                                    region_window = region
                                    break
                            if region_window:
                                return window, area, region_window, space
    return None, None, None, None

def _operator_delete_selected(window, area, region, space) -> bool:
    """Führt den eigentlichen Operator im Override-Kontext aus."""
    try:
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
            if hasattr(bpy.ops.clip, 'delete_track'):
                res = bpy.ops.clip.delete_track()
                return 'CANCELLED' not in res
            for name in ['tracking_track_delete', 'track_remove']:
                if hasattr(bpy.ops.clip, name):
                    res = getattr(bpy.ops.clip, name)()
                    if 'CANCELLED' not in res:
                        return True
    except Exception:
        pass
    return False

def delete_track_by_name(context, track_name: str) -> bool:
    """Löscht einen kompletten Track (alle Marker) über Operator-Selektion."""
    return delete_tracks_by_names(context, [track_name]) == 1

def delete_tracks_by_names(context, track_names: Iterable[str]) -> int:

    tracking = _get_tracking(context)
    if tracking is None:
        return 0

    clip = bpy.context.space_data.clip if getattr(bpy.context, 'space_data', None) else None
    tracks = tracking.tracks

    unique: List[str] = list(dict.fromkeys(track_names))
    targets = [tracks.get(name) for name in unique if tracks.get(name) is not None]
    if not targets:
        return 0

    # Auswahl zurücksetzen
    for tr in tracks:
        try:
            tr.select = False
        except Exception:
            pass

    # Auswahl setzen
    for tr in targets:
        try:
            tr.select = True
        except Exception:
            pass

    before = len(tracks)
    window, area, region, space = _find_clip_editor_area(clip)
    if not window:
        return 0
    if not _operator_delete_selected(window, area, region, space):
        return 0
    after = len(tracks)
    removed = max(0, before - after)
    return removed
