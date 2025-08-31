from __future__ import annotations
import math
from typing import Dict, Any, List, Tuple, Optional
import sys
import bpy

__all__ = ("run_reduce_error_tracks", "get_avg_reprojection_error")

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _resolve_clip(context: bpy.types.Context):
    """Ermittelt den aktiven MovieClip aus Context, Space oder Datenbank."""
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip


def _active_tracking_object(clip) -> Optional[bpy.types.MovieTrackingObject]:
    """Gibt das aktive Tracking-Objekt zurück (bevorzugt 'active', sonst 'Camera'/erstes)."""
    try:
        tr = clip.tracking
        objs = getattr(tr, "objects", None)
        if not objs:
            return None
        # bevorzugt active
        active = getattr(objs, "active", None)
        if active:
            return active
        # sonst 'Camera'
        for o in objs:
            if o.name == "Camera":
                return o
        # sonst erstes
        return objs[0] if len(objs) else None
    except Exception:
        return None


def _find_clip_area_and_region(context: bpy.types.Context):
    """Sucht eine CLIP_EDITOR Area/Region für Operator-Overrides."""
    try:
        window = context.window
        if not window:
            return None, None, None
        screen = window.screen
        if not screen:
            return None, None, None
        for area in screen.areas:
            if area.type == 'CLIP_EDITOR':
                # Bevorzugt die 'WINDOW'-Region
                region_window = None
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region_window = region
                        break
                # aktiver Space
                space = None
                for sp in area.spaces:
                    if sp.type == 'CLIP_EDITOR':
                        space = sp
                        break
                return area, region_window, space
    except Exception:
        pass
    return None, None, None


def _clip_op_override(context: bpy.types.Context, clip, obj: Optional[bpy.types.MovieTrackingObject] = None) -> Dict[str, Any] | None:
    """
    Baut einen Override-Kontext für Clip-Editor-Operatoren. Setzt zusätzlich – wenn möglich –
    das aktive Tracking-Objekt auf 'obj', damit der Operator die Selektion richtig auswertet.
    Fällt auf None zurück, wenn nicht möglich.
    """
    area, region, space = _find_clip_area_and_region(context)
    if not area or not region or not space:
        return None
    override = {
        "window": context.window,
        "screen": context.window.screen if context.window else None,
        "area": area,
        "region": region,
        "scene": context.scene,
        "space_data": space,
        "edit_movieclip": clip,
    }
    # sicherstellen, dass Space den Clip hält
    try:
        space.clip = clip
    except Exception:
        pass
    # Space-Modus (Tracking) sicherstellen – Operatoren erwarten TRACKING
    try:
        if hasattr(space, "mode") and space.mode != 'TRACKING':
            space.mode = 'TRACKING'
    except Exception:
        pass
    # aktives Tracking-Objekt setzen (entscheidend für clip.delete_track)
    try:
        tr = clip.tracking
        if obj is not None and hasattr(tr, "objects"):
            # Blender erwartet für Operatoren i. d. R. das aktive Objekt
            if tr.objects.active is not obj:
                tr.objects.active = obj
    except Exception:
        # nicht fatal – Operator kann ggf. trotzdem greifen
        pass
    return override


def _err_value(track) -> float:
    """Liest average_error robust; NaN/fehlend -> -1.0 (ungültig)."""
    try:
        v = float(getattr(track, "average_error", float("nan")))
        return v if (v == v and v >= 0.0) else -1.0
    except Exception:
        return -1.0


def _track_len(track) -> int:
    """Länge eines Tracks über Marker-Anzahl (Fallback-Kriterium)."""
    try:
        return len(track.markers)
    except Exception:
        return 0


def _select_tracks_by_name(obj: bpy.types.MovieTrackingObject, names: List[str]) -> int:
    """Selektiert in obj.tracks alle Tracks, deren name in names ist. Gibt Selektionsanzahl zurück."""
    cnt = 0
    for trk in obj.tracks:
        sel = (trk.name in names)
        trk.select = sel
        if sel:
            cnt += 1
    return cnt


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def get_avg_reprojection_error(context: bpy.types.Context) -> float | None:
    """
    Liefert den durchschnittlichen Solve-Error in Pixeln, wenn vorhanden.
    Primär: reconstruction.average_error des aktiven Tracking-Objekts.
    Fallback: Mittelwert der Track.average_error über alle Tracks mit gültigem Wert im aktiven Objekt.
    """
    clip = _resolve_clip(context)
    if not clip:
        return None

    # Primärquelle: Reconstruction des aktiven Objekts
    try:
        obj = _active_tracking_object(clip)
        if obj and obj.reconstruction and getattr(obj.reconstruction, "is_valid", False):
            ae = float(getattr(obj.reconstruction, "average_error", float("nan")))
            if ae == ae and ae > 0.0:  # not NaN
                return ae
    except Exception:
        pass

    # Fallback: Durchschnitt der gültigen Fehler im aktiven Objekt
    try:
        obj = _active_tracking_object(clip)
        if not obj:
            return None
        vals: List[float] = []
        for t in obj.tracks:
            v = _err_value(t)
            if v >= 0.0:
                vals.append(v)
        if not vals:
            return None
        return sum(vals) / len(vals)
    except Exception:
        return None


def run_reduce_error_tracks(
    context: bpy.types.Context,
    *,
    max_to_delete: int,
    object_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Löscht bis zu 'max_to_delete' Tracks mit dem höchsten average_error im aktiven (oder benannten) Tracking-Objekt.
    Implementiert Löschung via Operator (bpy.ops.clip.delete_track), um UI/Depsgraph/Undo konsistent zu halten.

    Rückgabe:
      {
        "status": "OK" | "NOOP" | "NO_CLIP" | "NO_OBJECT" | "NO_VALID_ERRORS",
        "mode": "ERROR_BASED" | "LEN_FALLBACK" | None,
        "object": "<Objektname>" | None,
        "deleted": <int>,
        "before": <int>,
        "after": <int>,
        "names": [<gelöschte Tracknamen>]
      }
    """
    if max_to_delete <= 0:
        return {"status": "NOOP", "mode": None, "object": None, "deleted": 0, "before": 0, "after": 0, "names": []}

    clip = _resolve_clip(context)
    if not clip:
        return {"status": "NO_CLIP", "mode": None, "object": None, "deleted": 0, "before": 0, "after": 0, "names": []}

    # Objektwahl
    tr = clip.tracking
    obj: Optional[bpy.types.MovieTrackingObject] = None
    try:
        if object_name:
            for o in tr.objects:
                if o.name == object_name:
                    obj = o
                    break
        if obj is None:
            obj = _active_tracking_object(clip)
    except Exception:
        obj = None

    if obj is None:
        return {"status": "NO_OBJECT", "mode": None, "object": None, "deleted": 0, "before": 0, "after": 0, "names": []}

    # Arbeitsmenge
    tracks_all = list(obj.tracks)
    before_cnt = len(tracks_all)
    if before_cnt == 0:
        return {"status": "NOOP", "mode": None, "object": obj.name, "deleted": 0, "before": 0, "after": 0, "names": []}

    # Sortierung nach Fehler (absteigend), ungültige (-1) nach hinten
    tracks_sorted = sorted(tracks_all, key=_err_value, reverse=True)
    worst_valid = [t for t in tracks_sorted if _err_value(t) >= 0.0]

    # Fallback: Keine validen Fehler -> benutze kürzeste Tracks als Kandidaten (meist wertlos)
    mode = "ERROR_BASED"
    candidates: List[bpy.types.MovieTrackingTrack]
    if not worst_valid:
        candidates = sorted(tracks_all, key=_track_len)  # aufsteigend (kürzeste zuerst)
        mode = "LEN_FALLBACK"
    else:
        candidates = worst_valid

    k = min(int(max_to_delete), max(1, len(candidates)))
    to_remove = candidates[:k]
    names = [t.name for t in to_remove]

    # Selektion aufbauen
    selected_count = _select_tracks_by_name(obj, names)
    if selected_count == 0:
        # nichts selektiert -> nichts zu löschen
        after_cnt = len(obj.tracks)
        return {
            "status": "NOOP",
            "mode": mode,
            "object": obj.name,
            "deleted": 0,
            "before": before_cnt,
            "after": after_cnt,
            "names": [],
        }

    # Operator-Kontext ermitteln
    override = _clip_op_override(context, clip, obj)

    # Löschen via Operator (kontextsensitiv & undo-sicher)
    op_failed_exc: Optional[Exception] = None
    if override:
        try:
            # KORREKT: Kontext via temp_override injizieren, Operator ohne dict-Arg aufrufen
            with bpy.context.temp_override(**override):
                bpy.ops.clip.delete_track(confirm=False)
        except Exception as ex:
            op_failed_exc = ex
    else:
        # Fallback: globaler Kontext (kann scheitern; API-Fallback greift dann)
        try:
            bpy.ops.clip.delete_track(confirm=False)
        except Exception as ex:
            op_failed_exc = ex

    # Depsgraph/UI refresh (Operator macht i. d. R. genug, wir sichern ab)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    after_cnt = len(obj.tracks)
    deleted = max(0, before_cnt - after_cnt)  # tatsächliche Differenz nach Operator

    # --- ROBUST FALLBACK ----------------------------------------------------
    # Wenn Operator scheitert oder kein Track gelöscht wurde, lösche direkt via API.
    if deleted == 0:
        # Optionales Debug für Diagnose
        try:
            print(f"[ReduceErrorTracks] Operator result → deleted=0; fallback=API ({'with exc' if op_failed_exc else 'no exc'})", file=sys.stderr)
            if op_failed_exc:
                print(f"[ReduceErrorTracks] OP_FAILED: {op_failed_exc}", file=sys.stderr)
        except Exception:
            pass
        api_deleted = 0
        # Sicherheitskopie, weil remove() die Liste invalidiert
        for t in list(to_remove):
            try:
                if t in obj.tracks:
                    obj.tracks.remove(t)
                    api_deleted += 1
            except Exception:
                # continue trying others
                pass
        # Refresh
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        after_cnt = len(obj.tracks)
        deleted = api_deleted
        # Wenn die API weniger/länger löscht, trimmen wir Namen konservativ
        if deleted < len(names):
            names = names[:deleted]

    return {
        "status": "OK",
        "mode": mode,
        "object": obj.name,
        "deleted": deleted,
        "before": before_cnt,
        "after": after_cnt,
        "names": names,
    }
