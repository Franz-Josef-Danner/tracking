from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Iterable
import math
import bpy
import time
from ..Operator import tracking_coordinator as tco

__all__ = (
    "run_projection_cleanup_builtin",
)

# -----------------------------------------------------------------------------
# Kontext- und Error-Utilities (unverändert / leicht ergänzt)
# -----------------------------------------------------------------------------


def _find_clip_window(context) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None, None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            if region_window:
                return area, region_window, area.spaces.active
    return None, None, None


def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _get_current_solve_error_now(context) -> Optional[float]:
    clip = _active_clip(context)
    if not clip:
        return None
    try:
        recon = clip.tracking.objects.active.reconstruction
    except Exception:
        return None
    if not getattr(recon, "is_valid", False):
        return None

    if hasattr(recon, "average_error"):
        try:
            return float(recon.average_error)
        except Exception:
            pass

    try:
        errs = [float(c.average_error) for c in getattr(recon, "cameras", [])]
        if not errs:
            return None
        return sum(errs) / len(errs)
    except Exception:
        return None


def _poke_update():
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


def _wait_until_error(context, *, wait_forever: bool, timeout_s: float, tick_s: float = 0.25) -> Optional[float]:
    """Wartet, bis ein gültiger Solve-Error verfügbar ist (optional endlos / mit Timeout)."""
    deadline = time.monotonic() + float(timeout_s)
    ticks = 0
    while True:
        err = _get_current_solve_error_now(context)
        if err is not None:
            print(f"[CleanupWait] Solve-Error verfügbar: {err:.4f}px (after {ticks} ticks)")
            return err

        _poke_update()
        ticks += 1

        if not wait_forever and time.monotonic() >= deadline:
            print(f"[CleanupWait] Timeout nach {timeout_s:.1f}s – kein gültiger Error verfügbar.")
            return None

        try:
            time.sleep(max(0.0, float(tick_s)))
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Track-Iteration / Hilfsfunktionen
# -----------------------------------------------------------------------------


def _iter_tracks_with_obj(clip: Optional[bpy.types.MovieClip]) -> Iterable[tuple[bpy.types.MovieTrackingObject, bpy.types.MovieTrackingTrack]]:
    """Iteriert alle Tracks inkl. zugehörigem Tracking-Objekt."""
    if not clip:
        return []
    try:
        for obj in clip.tracking.objects:
            for t in obj.tracks:
                yield obj, t
    except Exception:
        return []


def _count_tracks(clip: Optional[bpy.types.MovieClip]) -> int:
    return sum(1 for _ in _iter_tracks_with_obj(clip))


def _clear_selection(clip: Optional[bpy.types.MovieClip]) -> None:
    for _, t in _iter_tracks_with_obj(clip):
        try:
            if getattr(t, "select", False):
                t.select = False
        except Exception:
            pass


def _allowed_actions() -> set[str]:
    try:
        props = bpy.ops.clip.clean_tracks.get_rna_type().properties
        return {e.identifier for e in props['action'].enum_items}
    except Exception:
        return {'SELECT', 'DELETE_TRACK', 'DELETE_SEGMENTS'}


def _invoke_clean_tracks(context, *, used_error: float, action: str) -> None:
    area, region, space = _find_clip_window(context)
    if area and region and space:
        override = dict(area=area, region=region, space_data=space)
    else:
        override = {}

    try:
        with context.temp_override(**override):
            bpy.ops.clip.clean_tracks(clean_error=float(used_error), action=str(action))
    except TypeError:
        with context.temp_override(**override):
            bpy.ops.clip.clean_tracks(error=float(used_error), action=str(action))


# -----------------------------------------------------------------------------
# NEU: Nur den Track mit dem höchsten (durchschnittlichen) Reprojektion-Error entfernen
# -----------------------------------------------------------------------------


def _safe_track_error(track: bpy.types.MovieTrackingTrack) -> float:
    """Liest track.average_error robust (NaN/None -> -inf)."""
    try:
        val = float(getattr(track, "average_error", float("nan")))
        if math.isnan(val) or math.isinf(val):
            return float("-inf")
        return val
    except Exception:
        return float("-inf")


def _find_worst_track(clip: Optional[bpy.types.MovieClip]) -> Optional[tuple[bpy.types.MovieTrackingObject, bpy.types.MovieTrackingTrack, float]]:
    """Gibt (obj, track, error) für den Track mit dem höchsten average_error zurück."""
    worst: Optional[tuple[bpy.types.MovieTrackingObject, bpy.types.MovieTrackingTrack, float]] = None
    for obj, t in _iter_tracks_with_obj(clip):
        err = _safe_track_error(t)
        if worst is None or err > worst[2]:
            worst = (obj, t, err)
    # Falls alle -inf (keine nutzbaren Errors), None zurückgeben
    if worst and worst[2] == float("-inf"):
        return None
    return worst


def _delete_track(obj: bpy.types.MovieTrackingObject, track: bpy.types.MovieTrackingTrack) -> bool:
    """Entfernt einen Track sicher aus seinem Objekt. Liefert True bei Erfolg."""
    try:
        obj.tracks.remove(track)
        return True
    except Exception as ex:
        print(f"[Cleanup] Konnte Track nicht löschen: {ex!r}")
        return False


# -----------------------------------------------------------------------------
# Öffentliche API
# -----------------------------------------------------------------------------


def run_projection_cleanup_builtin(
    context: bpy.types.Context,
    *,
    # Bestehende Parameter bleiben für Rückwärtskompatibilität erhalten
    error_limit: float | None = None,
    threshold: float | None = None,
    max_error: float | None = None,
    wait_for_error: bool = True,
    wait_forever: bool = False,
    timeout_s: float = 20.0,
    action: str = "DELETE_SEGMENTS",
    # NEU:
    delete_worst_only: bool = True,
) -> Dict[str, Any]:
    """
    Führt Reprojection-Cleanup aus.

    Standardmodus (delete_worst_only=True):
        - ermittelt den *einzelnen* Track mit dem höchsten ``average_error`` und löscht nur diesen.

    Kompatibilitätsmodus (delete_worst_only=False):
        - identisch zum bisherigen Verhalten: nutzt ``bpy.ops.clip.clean_tracks`` mit Schwellwert.
    """
    clip = _active_clip(context)
    before_count = _count_tracks(clip)

    if delete_worst_only:
        worst = _find_worst_track(clip)
        if worst is None:
            print("[Cleanup] Kein Track mit gültigem average_error gefunden – Vorgang wird übersprungen.")
            result = {
                "status": "SKIPPED",
                "reason": "no_valid_track_error",
                "used_error": None,
                "action": "DELETE_SINGLE_WORST",
                "before": before_count,
                "after": before_count,
                "deleted": 0,
                "selected": 0,
                "disabled": 0,
            }
            tco.on_projection_cleanup_finished(context=context)
            return result

        obj, track, err = worst
        name = getattr(track, "name", "<unnamed>")
        print(f"[Cleanup] Lösche schlechtesten Track: {name} (avg_err={err:.4f}px)")
        ok = _delete_track(obj, track)
        after_count = _count_tracks(clip)
        deleted = 1 if ok and after_count == max(0, before_count - 1) else 0

        result = {
            "status": "OK" if ok else "ERROR",
            "used_error": err,
            "action": "DELETE_SINGLE_WORST",
            "reason": None if ok else "remove_failed",
            "before": before_count,
            "after": after_count,
            "deleted": deleted,
            "selected": 0,
            "disabled": 0,
            "track_name": name,
        }
        tco.on_projection_cleanup_finished(context=context)
        return result

    # ---- Altmodus (Schwellwert-basierter Cleanup) ----
    used_error: Optional[float] = None
    for val in (error_limit, threshold, max_error):
        if val is not None:
            used_error = float(val)
            break

    if used_error is None and wait_for_error:
        print("[Cleanup] Kein Error übergeben → warte auf Solve-Error …")
        used_error = _wait_until_error(context, wait_forever=bool(wait_forever), timeout_s=float(timeout_s))

    if used_error is None:
        print("[Cleanup] Kein gültiger Solve-Error verfügbar – Cleanup wird SKIPPED.")
        return {
            "status": "SKIPPED",
            "reason": "no_error",
            "used_error": None,
            "action": action,
            "before": before_count,
            "after": before_count,
            "deleted": 0,
            "selected": 0,
            "disabled": 0,
        }

    used_error = float(used_error) * 1.2
    print(f"[Cleanup] Starte clean_tracks mit Grenzwert {used_error:.4f}px, action={action}")

    try:
        _invoke_clean_tracks(context, used_error=float(used_error), action=str(action if action in _allowed_actions() else "SELECT"))
    except Exception as ex:
        print(f"[Cleanup] Fehler bei clean_tracks: {ex!r}")
        return {
            "status": "ERROR",
            "reason": repr(ex),
            "used_error": used_error,
            "action": action,
            "before": before_count,
            "after": before_count,
            "deleted": 0,
            "selected": 0,
            "disabled": 0,
        }

    after_count = _count_tracks(clip)
    deleted = max(0, (before_count or 0) - (after_count or 0))

    print(
        f"[Cleanup] Cleanup abgeschlossen. Vorher={before_count}, nachher={after_count}, entfernt={deleted}"
    )

    tco.on_projection_cleanup_finished(context=context)

    return {
        "status": "OK",
        "used_error": used_error,
        "action": action,
        "reason": None,
        "before": before_count,
        "after": after_count,
        "deleted": deleted,
        "selected": 0,
        "disabled": 0,
    }
