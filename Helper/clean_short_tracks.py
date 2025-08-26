# Helper/clean_short_tracks.py — Short-Track-Cleaner nach dem Tracking
# Nutzt ausschließlich Blender-Operatoren (clean_tracks / delete_track).
# Respektiert __skip_clean_short_once und __just_created_names aus Detect.

import bpy
from typing import List, Optional, Tuple, Iterable, Set

# Keys, die mit Detect/Coordinator abgestimmt sind
KEY_SKIP_ONCE = "__skip_clean_short_once"
KEY_FRESH     = "__just_created_names"   # Liste frisch angelegter Track-Namen

# ---------------------------------------------------------------------------
# kleine Utils

def _get_clip_from_ui() -> Optional[bpy.types.MovieClip]:
    wm = bpy.context.window_manager
    if not wm:
        return None
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space and getattr(space, "clip", None):
                return space.clip
    return None

def _find_clip_and_ui() -> Tuple[Optional[bpy.types.MovieClip], Optional[bpy.types.Window], Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
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
    # Fallbacks: Context / erstes MovieClip
    clip = getattr(bpy.context, "edit_movieclip", None)
    if not clip and bpy.data.movieclips:
        clip = bpy.data.movieclips[0]
    return clip, None, None, None, None

def _get_fresh_names(scene: bpy.types.Scene) -> Set[str]:
    try:
        vals = scene.get(KEY_FRESH, [])
        # ID-Props sind einfache Typen; sicher auf str mappen
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
    """Selektiert nur Tracks, deren Namen in allow enthalten sind; gibt Anzahl zurück."""
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
    out = set()
    for t in tracks:
        n = str(getattr(t, "name", ""))
        if n:
            out.add(n)
    return out

def _is_empty_or_fully_muted(track: bpy.types.MovieTrackingTrack) -> bool:
    """Leere Hülle oder alle Marker gemutet? (nur lesen, nichts setzen)"""
    try:
        markers = track.markers
        if len(markers) == 0:
            return True
        # Bei manchen Builds haben Marker eine .mute-Flag – falls nicht vorhanden, ignorieren wir’s.
        has_any = False
        for m in markers:
            has_any = True
            if not getattr(m, "mute", False):
                return False
        return has_any  # alle gemutet
    except Exception:
        # Wenn wir nicht zuverlässig prüfen können, lieber nichts machen
        return False

# ---------------------------------------------------------------------------
# Kernfunktion

def clean_short_tracks(
    context: bpy.types.Context = bpy.context,
    min_len: Optional[int] = None,
    action: str = "DELETE_TRACK",     # 'SELECT' | 'DELETE_TRACK' | 'DELETE_SEGMENTS'
    respect_fresh: bool = True,
    verbose: bool = True,
) -> Tuple[int, int]:
    """
    Bereinigt Short-Tracks ausschließlich mit Blender-Operatoren.
    - Schont frisch erzeugte Tracks (scene['__just_created_names']).
    - Einmaliges Skip über scene['__skip_clean_short_once'].
    - Vor-/Nach-Pass löscht leere bzw. komplett gemutete Hüllen.

    Rückgabe: (geprüft_tracks, geändert_tracks) – geändert ~ Anzahl gelöschter Tracks.
    """
    scn = context.scene
    if scn is None:
        if verbose:
            print("[CleanShort] WARN: Keine aktive Szene.")
        return 0, 0

    # einmaliges Gate
    if scn.get(KEY_SKIP_ONCE, False):
        if verbose:
            print("[CleanShort] Skip (Gate __skip_clean_short_once gesetzt).")
        try:
            scn[KEY_SKIP_ONCE] = False
        except Exception:
            pass
        return 0, 0

    # Parameter aus Szene ableiten (kompatibel zu deinen Defaults)
    frames = int(min_len) if min_len is not None else int(getattr(scn, "frames_track", 25) or 25)
    frames = max(frames, 1)
    error_val = float(getattr(scn, "clean_error", 2.0) or 2.0)

    clip, window, area, region, space = _find_clip_and_ui()
    if not clip:
        if verbose:
            print("[CleanShort] WARN: Kein MovieClip gefunden.")
        return 0, 0

    tracks = clip.tracking.tracks
    total_before = len(tracks)
    processed = total_before

    # Frischliste (zum Schonung-Set)
    fresh = _get_fresh_names(scn) if respect_fresh else set()

    # --------------------------- Vor-Pass: leere/fully-muted Hüllen löschen
    pre_names = _names_set(tracks)
    pre_hulls = {t for t in tracks if _is_empty_or_fully_muted(t)}
    if pre_hulls:
        _deselect_all(tracks)
        allow = {str(getattr(t, "name", "")) for t in pre_hulls}
        _select_names(tracks, allow)
        # Operator im passenden Kontext ausführen
        try:
            if window and area and region and space:
                with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region, space_data=space, scene=scn):
                    bpy.ops.clip.delete_track()
            else:
                # Wenn kein UI-Override möglich ist, hoffen wir auf aktuellen Kontext
                bpy.ops.clip.delete_track()
        except Exception as ex:
            if verbose:
                print(f"[CleanShort] WARN: Pre-Delete via Operator fehlgeschlagen: {ex!s}")

    # --------------------------- Haupt-Pass: clean_tracks für alle außer “fresh”
    names_now = _names_set(tracks)
    eligible = names_now - fresh  # nur diese selektieren
    if eligible:
        _deselect_all(tracks)
        _select_names(tracks, eligible)
        try:
            if window and area and region and space:
                with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region, space_data=space, scene=scn):
                    bpy.ops.clip.clean_tracks(frames=frames, error=error_val, action=action)
            else:
                bpy.ops.clip.clean_tracks(frames=frames, error=error_val, action=action)
        except Exception as ex:
            if verbose:
                print(f"[CleanShort] WARN: clean_tracks Operator fehlgeschlagen: {ex!s}")

    # --------------------------- Nach-Pass: neu entstandene Hüllen entsorgen
    post_hulls = {t for t in tracks if _is_empty_or_fully_muted(t)}
    if post_hulls:
        _deselect_all(tracks)
        allow = {str(getattr(t, "name", "")) for t in post_hulls}
        _select_names(tracks, allow)
        try:
            if window and area and region and space:
                with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region, space_data=space, scene=scn):
                    bpy.ops.clip.delete_track()
            else:
                bpy.ops.clip.delete_track()
        except Exception as ex:
            if verbose:
                print(f"[CleanShort] WARN: Post-Delete via Operator fehlgeschlagen: {ex!s}")

    total_after = len(clip.tracking.tracks)
    affected = max(0, total_before - total_after) if action == "DELETE_TRACK" else 0

    if verbose:
        print(f"[CleanShort] Tracks < {frames} Frames wurden bearbeitet. Aktion: {action} | "
              f"geprüft={processed}, geändert={affected}")

    # Frischliste auf noch existierende Namen eindampfen
    if respect_fresh and fresh:
        still = _names_set(clip.tracking.tracks)
        try:
            scn[KEY_FRESH] = [n for n in fresh if n in still]
        except Exception:
            pass

    return processed, affected
