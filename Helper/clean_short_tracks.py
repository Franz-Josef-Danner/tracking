# Helper/clean_short_tracks.py
# — echter Short-Track-Cleaner NACH dem Tracking.
# Führt IMMER einen Clean-Call aus und schützt frisch erzeugte Tracks
# über Deselektion (statt die gesamte Clean-Phase zu überspringen).
# Zusätzlich: robuste Clip-Ermittlung, CLIP_EDITOR-Override, String-Sanitizing.

from __future__ import annotations

import bpy
from typing import Any, Dict, Iterable, List, Optional

__all__ = ("clean_short_tracks",)


def _clip_override(context: bpy.types.Context) -> Optional[Dict[str, Any]]:
    """Sicheren CLIP_EDITOR-Override bereitstellen (oder None)."""
    win = getattr(context, "window", None)
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == "CLIP_EDITOR":
            for region in area.regions:
                if region.type == "WINDOW":
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
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None


def _coerce_utf8_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, (bytes, bytearray)):
        b = bytes(x)
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return b.decode(enc).strip()
            except Exception:
                continue
        return None
    try:
        s = str(x).strip()
        return s or None
    except Exception:
        return None


def _coerce_utf8_str_list(seq: Iterable[Any]) -> List[str]:
    return [s for s in (_coerce_utf8_str(x) for x in (seq or [])) if s]


def _delete_selected_tracks_with_override(override: Optional[Dict[str, Any]]) -> None:
    """Selektierte Tracks löschen, optional mit UI-Override."""
    if override:
        with bpy.context.temp_override(**override):
            bpy.ops.clip.delete_track()
    else:
        bpy.ops.clip.delete_track()


def _clean_tracks_with_override(
    override: Optional[Dict[str, Any]], *, frames: int, action: str
) -> None:
    """Clean-Call, optional mit UI-Override."""
    if override:
        with bpy.context.temp_override(**override):
            bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=action)
    else:
        bpy.ops.clip.clean_tracks(frames=frames, error=0.0, action=action)


def clean_short_tracks(
    context: bpy.types.Context, *, frames: Optional[int] = None, action: str = "DELETE_TRACK"
) -> set:
    """
    Löscht/selektiert Tracks mit weniger Frames als 'frames'.
    WICHTIG: Läuft IMMER, es gibt KEINE 'skip once'-Schonfrist.
    Schutz für frisch angelegte Tracks erfolgt durch Deselektion ihrer Namen.

    Respektiert:
      - scene["pipeline_do_not_start"]       (harte Sperre, wenn die Pipeline nicht laufen darf)
      - scene["__just_created_names"]        (Schutzliste, UTF‑8-sanitized; wird nach dem Lauf geleert)
    """
    scene = context.scene

    # Harte Gate-Sperre
    if scene.get("pipeline_do_not_start", False):
        print("[CleanShort] blocked by pipeline_do_not_start")
        return {"CANCELLED"}

    # Frames ermitteln (Default: scene.frames_track)
    if frames is None:
        if not hasattr(scene, "frames_track"):
            print("[CleanShort] Fehler: Scene.frames_track nicht definiert")
            return {"CANCELLED"}
        try:
            frames = int(scene.frames_track)
        except Exception:
            frames = 25
    frames = max(int(frames), 1)

    clip = _resolve_clip(context)
    if clip is None:
        print("[CleanShort] Fehler: Kein MovieClip verfügbar / kein CLIP_EDITOR Kontext gefunden")
        return {"CANCELLED"}

    override = _clip_override(context)
    tracks = clip.tracking.tracks

    # Frische Namen schützen (Sanitizing)
    fresh_raw = scene.get("__just_created_names", []) or []
    fresh = set(_coerce_utf8_str_list(fresh_raw))
    if fresh_raw and (len(fresh) != len(fresh_raw)):
        print("[CleanShort] normalized __just_created_names")

    # Pre-Pass: offensichtliche Leichen entfernen (nur bei Delete)
    if action == "DELETE_TRACK":
        to_delete = [
            t
            for t in tracks
            if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)
        ]
        if to_delete:
            for t in tracks:
                t.select = False
            for t in to_delete:
                t.select = True
            _delete_selected_tracks_with_override(override)

    # Clean: alle selektieren, frische Namen abwählen (Schutz, aber kein Skip der gesamten Phase)
    for t in tracks:
        t.select = True
    if fresh:
        for t in tracks:
            if t.name in fresh:
                t.select = False

    # Clean ausführen
    try:
        _clean_tracks_with_override(override, frames=frames, action=action)
    except Exception as ex:
        print("[CleanShort] clean_tracks failed:", ex)
        return {"CANCELLED"}

    # Post-Pass: neu entstandene Hüllen entfernen (nur bei Delete)
    if action == "DELETE_TRACK":
        tracks = clip.tracking.tracks  # refresh
        to_delete = [
            t
            for t in tracks
            if (len(t.markers) == 0) or all(getattr(m, "mute", False) for m in t.markers)
        ]
        if to_delete:
            for t in tracks:
                t.select = False
            for t in to_delete:
                t.select = True
            _delete_selected_tracks_with_override(override)

    # Schutzliste leeren – Schutz war nur einmal nötig
    if fresh:
        try:
            scene["__just_created_names"] = []
        except Exception:
            pass

    print(f"[CleanShort] Tracks < {int(frames)} Frames wurden bearbeitet. Aktion: {action}")
    return {"FINISHED"}
