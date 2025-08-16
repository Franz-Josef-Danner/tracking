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
# ---------------------------------------------------------------------------

def _clip_override(context: bpy.types.Context) -> Optional[Dict[str, Any]]:
    """Sicheren CLIP_EDITOR-Override bereitstellen (oder None)."""
    win = getattr(context, "window", None)
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {
                        "window": win,
                        "screen": win.screen,
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                        "scene": context.scene,
                    }
    return None


def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Clip robust bestimmen: bevorzugt aktiver CLIP_EDITOR, sonst erstes MovieClip."""
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    if clip:
        return clip
    try:
        # Fallback: erstes MovieClip im File
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# UTF-8 Hardening
# ---------------------------------------------------------------------------

def _coerce_utf8_str(x: Any) -> str:
    """Konservativ in druckbaren str wandeln: utf-8 → latin-1 Fallback; unprintables -> '_'."""
    if x is None:
        return ""
    if isinstance(x, str):
        s = x
    elif isinstance(x, (bytes, bytearray, memoryview)):
        b = bytes(x)
        try:
            s = b.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            # Harte Fälle (z. B. 0xF0 ohne gültige Fortsetzung): latin-1-Fallback
            s = b.decode("latin-1", errors="replace")
    else:
        s = str(x)
    # Nur druckbare Zeichen durchlassen
    return "".join(ch if ch.isprintable() else "_" for ch in s)


def _ensure_text_list(x: Any) -> List[str]:
    """Liste sauberer Strings zurückgeben; droppt Leereinträge."""
    out: List[str] = []
    if not x:
        return out
    seq = x if isinstance(x, (list, tuple)) else [x]
    for v in seq:
        s = _coerce_utf8_str(v).strip()
        if s:
            out.append(s)
    return out


def _try_set_scene_list(scene: bpy.types.Scene, key: str, seq: Iterable[str]) -> None:
    """Persistenz robust setzen (immer als saubere str-Liste)."""
    try:
        scene[key] = _ensure_text_list(list(seq))
    except Exception:
        # Letzte Verteidigungslinie: wenn Setzen scheitert, nicht crashen
        try:
            scene[key] = []
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Tracking Utilities
# ---------------------------------------------------------------------------

def _track_visible_length(tr: bpy.types.MovieTrackingTrack) -> int:
    """Zählt Marker mit sichtbaren Keys (nicht gemutet). 'Kurz' = wenige aktive Marker."""
    n = 0
    try:
        for m in tr.markers:
            if not m.mute:
                n += 1
    except Exception:
        # Defensive: bei API-Ausreißern nicht blockieren
        pass
    return n


def _mute_entire_track(tr: bpy.types.MovieTrackingTrack) -> None:
    """Track vollständig muten (Track-Flag, ansonsten Marker)."""
    try:
        # Einige Blender-Versionen haben tr.mute
        if hasattr(tr, "mute"):
            tr.mute = True
            return
    except Exception:
        pass
    # Fallback: Marker muten
    try:
        for m in tr.markers:
            m.mute = True
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def clean_short_tracks(
    context: bpy.types.Context,
    *,
    min_len: int = 25,
    action: str = "DELETE_TRACK",  # "DELETE_TRACK" | "MUTE_TRACK"
    protect_fresh: bool = True,
    verbose: bool = True,
) -> Tuple[int, int]:
    """
    Bereinigt 'kurze' Tracks nach dem Tracking. UTF-8 stabilisiert:
    - Säubert alle gelesenen/geschriebenen Namen/Listen (insb. __just_created_names).
    - Keine Umbenennung von Tracks.
    - Respektiert Gate-Flags aus Detect (Lock) und schützt Frischliste.

    Returns:
        (processed, affected)
        processed: Anzahl geprüfter Tracks
        affected:  Anzahl gelöschter/ gemuteter Tracks
    """
    scn = context.scene
    if scn.get(_LOCK_KEY, False):
        # Detect läuft noch; lieber nicht eingreifen
        if verbose:
            print("[CleanShort] Skip: Detect-Lock aktiv.")
        return 0, 0

    clip = _resolve_clip(context)
    if not clip:
        if verbose:
            print("[CleanShort] Kein aktiver MovieClip gefunden.")
        return 0, 0

    tracking = clip.tracking

    # --- Frisch-/Prev-Listen: LESEN → SÄUBERN → ZURÜCKSCHREIBEN ---
    fresh_raw = scn.get(KEY_FRESH, []) or []
    prev_raw  = scn.get(KEY_PREV, []) or []

    fresh_list = _ensure_text_list(fresh_raw)
    prev_list  = _ensure_text_list(prev_raw)

    # Rückschreiben (stellt sicher, dass Szene nie Bytes enthält)
    _try_set_scene_list(scn, KEY_FRESH, fresh_list)
    _try_set_scene_list(scn, KEY_PREV, prev_list)

    fresh = set(fresh_list) if protect_fresh else set()

    # --- Hauptdurchlauf ---
    processed = 0
    affected = 0

    to_delete: List[bpy.types.MovieTrackingTrack] = []
    to_mute: List[bpy.types.MovieTrackingTrack] = []

    # Snapshot der Namen (sanitisiert) für sichere Vergleiche
    def _safe_name(tr: bpy.types.MovieTrackingTrack) -> str:
        try:
            return _coerce_utf8_str(tr.name)
        except Exception:
            return ""

    for tr in list(tracking.tracks):
        processed += 1
        name = _safe_name(tr)

        # Frisch angelegte Tracks schützen (nie sofort löschen/muten)
        if name and name in fresh:
            continue

        length = _track_visible_length(tr)
        if length >= max(0, int(min_len)):
            continue

        if action == "DELETE_TRACK":
            to_delete.append(tr)
        else:
            to_mute.append(tr)

    # --- Aktionen ausführen (nur Datenblock-API, keine UI-Operatoren) ---
    if to_delete:
        for tr in to_delete:
            try:
                tracking.tracks.remove(tr)
                affected += 1
            except Exception as ex:
                if verbose:
                    print(f"[CleanShort] WARN: Entfernen von '{_safe_name(tr)}' fehlgeschlagen: {ex}")

    if to_mute:
        for tr in to_mute:
            try:
                _mute_entire_track(tr)
                affected += 1
            except Exception as ex:
                if verbose:
                    print(f"[CleanShort] WARN: Muten von '{_safe_name(tr)}' fehlgeschlagen: {ex}")

    # --- Persistenz nachziehen (Frischliste ggf. um gelöschte Namen bereinigen) ---
    if to_delete and protect_fresh and fresh:
        # Falls ein 'frischer' Track theoretisch gelöscht worden wäre (sollte durch Schutz nicht passieren),
        # bleibt die Frischliste dennoch sauber.
        still_exists = set()
        try:
            for tr in tracking.tracks:
                n = _coerce_utf8_str(tr.name).strip()
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
