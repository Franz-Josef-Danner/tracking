# Helper/clean_short_tracks.py — Short-Track-Cleaner NUR nach Länge
import bpy
from typing import Optional, Tuple, Iterable, Set

# Keys, die mit Detect/Coordinator abgestimmt sind
KEY_SKIP_ONCE = "__skip_clean_short_once"
KEY_FRESH     = "__just_created_names"   # Liste frisch angelegter Track-Namen

# ---------------------------------------------------------------------------
# kleine Utils

def _find_clip_and_ui() -> Tuple[
    Optional[bpy.types.MovieClip],
    Optional[bpy.types.Window],
    Optional[bpy.types.Area],
    Optional[bpy.types.Region],
    Optional[bpy.types.Space]
]:
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None, None
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                clip = getattr(space, "clip", None)
                return clip, window, area, region, space
    clip = getattr(bpy.context, "edit_movieclip", None)
    if not clip and bpy.data.movieclips:
        clip = bpy.data.movieclips[0]
    return clip, None, None, None, None


def _get_fresh_names(scene: bpy.types.Scene) -> Set[str]:
    try:
        vals = scene.get(KEY_FRESH, [])
        return {str(x) for x in (vals or [])}
    except Exception:
        return set()


def _deselect_all(tracks: Iterable[bpy.types.MovieTrackingTrack]) -> None:
    try:
        for t in tracks:
            t.select = False
    except Exception:
        pass


def _select_names(tracks: Iterable[bpy.types.MovieTrackingTrack], allow: Set[str]) -> int:
    n = 0
    for t in tracks:
        name = str(getattr(t, "name", ""))
        if name in allow:
            try:
                t.select = True
                n += 1
            except Exception:
                pass
    return n


def _names_set(tracks: Iterable[bpy.types.MovieTrackingTrack]) -> Set[str]:
    return {str(getattr(t, "name", "")) for t in tracks if getattr(t, "name", "")}


def _is_empty_or_fully_muted(track: bpy.types.MovieTrackingTrack) -> bool:
    try:
        markers = track.markers
        if len(markers) == 0:
            return True
        has_any = False
        for m in markers:
            has_any = True
            if not getattr(m, "mute", False):
                return False
        return has_any
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Kernfunktion (nur LÄNGEN-Prüfung)

def clean_short_tracks(
    context: bpy.types.Context = bpy.context,
    min_len: Optional[int] = None,
    action: str = "DELETE_TRACK",     # 'SELECT' | 'DELETE_TRACK' | 'DELETE_SEGMENTS'
    respect_fresh: bool = True,
    verbose: bool = False,            # bleibt für Kompatibilität, wird aber ignoriert
) -> Tuple[int, int]:
    scn = context.scene
    if scn is None:
        return 0, 0

    if scn.get(KEY_SKIP_ONCE, False):
        try:
            scn[KEY_SKIP_ONCE] = False
        except Exception:
            pass
        return 0, 0

    frames = int(min_len) if min_len is not None else int(getattr(scn, "frames_track", 25) or 25)
    frames = max(frames, 1)

    clip, window, area, region, space = _find_clip_and_ui()
    if not clip:
        return 0, 0

    tracks = clip.tracking.tracks
    total_before = len(tracks)
    processed = total_before

    fresh = _get_fresh_names(scn) if respect_fresh else set()

    pre_hulls = {t for t in tracks if _is_empty_or_fully_muted(t)}
    if pre_hulls:
        _deselect_all(tracks)
        allow = {str(getattr(t, "name", "")) for t in pre_hulls}
        _select_names(tracks, allow)
        try:
            if window and area and region and space:
                with bpy.context.temp_override(
                    window=window, screen=window.screen, area=area, region=region, space_data=space, scene=scn
                ):
                    bpy.ops.clip.delete_track()
            else:
                bpy.ops.clip.delete_track()
        except Exception:
            pass

    names_now = _names_set(clip.tracking.tracks)
    eligible = names_now - fresh
    if eligible:
        _deselect_all(clip.tracking.tracks)
        _select_names(clip.tracking.tracks, eligible)
        try:
            if window and area and region and space:
                with bpy.context.temp_override(
                    window=window, screen=window.screen, area=area, region=region, space_data=space, scene=scn
                ):
                    bpy.ops.clip.clean_tracks(frames=frames, action=action)
            else:
                bpy.ops.clip.clean_tracks(frames=frames, action=action)
        except Exception:
            pass

    post_hulls = {t for t in clip.tracking.tracks if _is_empty_or_fully_muted(t)}
    if post_hulls:
        _deselect_all(clip.tracking.tracks)
        allow = {str(getattr(t, "name", "")) for t in post_hulls}
        _select_names(clip.tracking.tracks, allow)
        try:
            if window and area and region and space:
                with bpy.context.temp_override(
                    window=window, screen=window.screen, area=area, region=region, space_data=space, scene=scn
                ):
                    bpy.ops.clip.delete_track()
            else:
                bpy.ops.clip.delete_track()
        except Exception:
            pass

    total_after = len(clip.tracking.tracks)
    affected = max(0, total_before - total_after) if action == "DELETE_TRACK" else 0

    if respect_fresh and fresh:
        still = _names_set(clip.tracking.tracks)
        try:
            scn[KEY_FRESH] = [n for n in fresh if n in still]
        except Exception:
            pass

    return processed, affected
