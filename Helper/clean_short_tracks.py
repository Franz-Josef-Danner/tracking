# Helper/clean_short_tracks.py — echter Short-Track-Cleaner NACH dem Tracking.
# UTF-8-Hardening: Säubert alle gelesenen/geschriebenen Strings (v. a. __just_created_names).
# Respektiert Gate-Flags aus Detect, schützt Frischliste, KEINE Umbenennung von Tracks.

import bpy
from typing import Iterable, List, Tuple, Dict, Any, Optional

__all__ = ("clean_short_tracks",)

# Gate-/Persistenzkeys (müssen mit Detect/Coordinator übereinstimmen)
_LOCK_KEY = "__detect_lock"
KEY_FRESH = "__just_created_names"   # Frisch angelegte Tracknamen aus Detect
KEY_PREV  = "detect_prev_names"      # Vorläuferliste aus Detect (optional)

# ---------------------------------------------------------------------------
# UI/Context Utilities (robust, ohne Zwang)

def _coerce_utf8_str(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, bytes):
        try:
            return s.decode("utf-8", errors="strict")
        except Exception:
            return s.decode("utf-8", errors="ignore")
    return str(s)

def _coerce_utf8_str_list(v: Any) -> List[str]:
    out: List[str] = []
    if isinstance(v, (list, tuple, set)):
        for x in v:
            out.append(_coerce_utf8_str(x))
    elif v is not None:
        out.append(_coerce_utf8_str(v))
    return out

def _try_get_scene_list(scn: bpy.types.Scene, key: str) -> List[str]:
    try:
        val = scn.get(key, [])
        return _coerce_utf8_str_list(val)
    except Exception:
        return []

def _try_set_scene_list(scn: bpy.types.Scene, key: str, value: List[str]) -> None:
    try:
        # ID-Props lassen nur simple Typen zu → Strings hart auf UTF-8 normieren
        scn[key] = [ _coerce_utf8_str(x) for x in (value or []) ]
    except Exception:
        pass

def _find_clip_editor_context() -> Tuple[Optional[bpy.types.Window], Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.SpaceClipEditor]]:
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return window, area, region, space
    return None, None, None, None

def _run_in_clip_context(op_callable, **kwargs):
    window, area, region, space = _find_clip_editor_context()
    if not (window and area and region and space):
        raise RuntimeError("No CLIP_EDITOR context available for operator.")
    override = {
        "window": window,
        "screen": window.screen,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    return op_callable(override, **kwargs)

def _deselect_all(clip: bpy.types.MovieClip):
    try:
        for t in clip.tracking.tracks:
            t.select = False
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Kernfunktion

def clean_short_tracks(
    context: bpy.types.Context = bpy.context,
    min_len: int = 25,
    action: str = "DELETE_TRACK",  # oder "MUTE_TRACK"
    respect_fresh: bool = True,
    verbose: bool = True,
) -> Tuple[int, int]:
    """
    Entfernt (oder mutet) alle Tracks mit < min_len Frames.
    Respektiert __skip_clean_short_once und __just_created_names.
    Robust gegen UI/Nicht-UI-Kontexte.
    """
    scn = context.scene
    if scn is None:
        if verbose:
            print("[CleanShort] WARN: Keine aktive Szene.")
        return 0, 0

    # Einmal-Gate: Detect kann CleanShort für genau einen Tick überspringen lassen
    if scn.get("__skip_clean_short_once", False):
        if verbose:
            print("[CleanShort] Skip (Gate __skip_clean_short_once gesetzt).")
        try:
            scn["__skip_clean_short_once"] = False
        except Exception:
            pass
        return 0, 0

    clip: Optional[bpy.types.MovieClip] = None
    # Versuche Clip sauber zu resolven (Space → Context → Daten)
    try:
        _, _, _, space = _find_clip_editor_context()
        if space and getattr(space, "clip", None):
            clip = space.clip
    except Exception:
        clip = None
    if not clip:
        # Fallback: aktueller Context
        clip = getattr(context, "edit_movieclip", None)
    if not clip and bpy.data.movieclips:
        # Letzte Eskalation: erstes MovieClip-Datenobjekt
        clip = bpy.data.movieclips[0]

    if not clip:
        if verbose:
            print("[CleanShort] WARN: Kein MovieClip gefunden.")
        return 0, 0

    # Frischliste einlesen (optional) und normalisieren
    fresh: List[str] = _try_get_scene_list(scn, KEY_FRESH) if respect_fresh else []
    fresh_set = set(fresh)

    to_delete: List[bpy.types.MovieTrackingTrack] = []
    to_mute: List[bpy.types.MovieTrackingTrack] = []
    processed = 0
    affected = 0

    # Kandidaten sammeln
    try:
        for t in list(clip.tracking.tracks):
            processed += 1
            name = _coerce_utf8_str(getattr(t, "name", ""))
            # frisch erzeugte Tracks in genau diesem Tick nicht anfassen
            if respect_fresh and name in fresh_set:
                continue

            # Minimale Länge bestimmen (Anzahl Marker → sichtbare Frames)
            try:
                track_len = sum(1 for _m in t.markers if getattr(_m, "co", None) is not None)
            except Exception:
                track_len = len(getattr(t, "markers", []))

            if track_len < min_len:
                if action == "DELETE_TRACK":
                    to_delete.append(t)
                else:
                    to_mute.append(t)
    except Exception as ex:
        if verbose:
            print(f"[CleanShort] WARN: Auflisten der Tracks fehlgeschlagen: {ex!s}")

    # Ausführung
    if to_mute:
        for t in to_mute:
            try:
                t.mute = True
                affected += 1
            except Exception as ex:
                if verbose:
                    print(f"[CleanShort] WARN: Muten von '{_coerce_utf8_str(getattr(t,'name',''))}' fehlgeschlagen: {ex!s}")

    if to_delete:
        # 1) Bevorzugt über Operator (löscht inkl. UI-Konsistenz)
        deleted_via_op = 0
        try:
            _deselect_all(clip)
            for t in to_delete:
                try:
                    t.select = True
                except Exception:
                    pass
            result = _run_in_clip_context(bpy.ops.clip.delete_track)
            if isinstance(result, set) and "FINISHED" in result:
                deleted_via_op = len(to_delete)
        except Exception as ex:
            if verbose:
                print(f"[CleanShort] WARN: Operator-Delete fehlgeschlagen: {ex!s}")

        # 2) Fallback auf Daten-API (pro Track)
        if deleted_via_op == 0:
            for t in to_delete:
                name = _coerce_utf8_str(getattr(t, "name", ""))
                try:
                    clip.tracking.tracks.remove(t)
                    affected += 1
                except Exception as ex:
                    # 3) Letzter Fallback: stumm schalten, falls Entfernen hart blockiert
                    try:
                        t.mute = True
                        affected += 1
                        if verbose:
                            print(f"[CleanShort] WARN: Entfernen von '{name}' fehlgeschlagen, Track gemutet: {ex!s}")
                    except Exception as ex2:
                        if verbose:
                            print(f"[CleanShort] WARN: Entfernen von '{name}' fehlgeschlagen: {ex!s} | zusätzliches Muten scheiterte: {ex2!s}")

    # Frischliste säubern: nur behalten, was noch existiert
    if respect_fresh and fresh:
        still_exists = set()
        try:
            for t in clip.tracking.tracks:
                n = _coerce_utf8_str(getattr(t, "name", ""))
                if n:
                    still_exists.add(n)
        except Exception:
            pass

        new_fresh = [n for n in fresh if n in still_exists]
        _try_set_scene_list(scn, KEY_FRESH, new_fresh)

    if verbose:
        act = "DELETE_TRACK" if action == "DELETE_TRACK" else "MUTE_TRACK"
        print(f"[CleanShort] Tracks < {min_len} Frames wurden bearbeitet. Aktion: {act} | "
              f"geprüft={processed}, geändert={affected}")

    return processed, affected
