from __future__ import annotations


from typing import Optional, Tuple, Dict, Any, Iterable
import bpy
import time
from ..Operator import tracking_coordinator as tco

__all__ = ("run_projection_cleanup_builtin",)


# -----------------------------------------------------------------------------
# Kontext- und Error-Utilities
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
# Zähl-/Hilfsfunktionen
# -----------------------------------------------------------------------------

def _iter_tracks(clip: Optional[bpy.types.MovieClip]) -> Iterable[bpy.types.MovieTrackingTrack]:
    if not clip:
        return []
    try:
        for obj in clip.tracking.objects:
            for t in obj.tracks:
                yield t
    except Exception:
        return []


def _count_tracks(clip: Optional[bpy.types.MovieClip]) -> int:
    """Anzahl aller Tracks im Clip."""
    return sum(1 for _ in _iter_tracks(clip))


def _count_selected(clip: Optional[bpy.types.MovieClip]) -> int:
    """Anzahl selektierter Tracks."""
    cnt = 0
    for t in _iter_tracks(clip):
        try:
            if getattr(t, "select", False):
                cnt += 1
        except Exception:
            pass
    return cnt


def _clear_selection(clip: Optional[bpy.types.MovieClip]) -> None:
    for t in _iter_tracks(clip):
        try:
            if getattr(t, "select", False):
                t.select = False
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Operator-Wrapper
# -----------------------------------------------------------------------------

def _allowed_actions() -> set[str]:
    """Liest die am Operator verfügbaren Enum-Aktionen (Fallback auf Standardliste)."""
    try:
        props = bpy.ops.clip.clean_tracks.get_rna_type().properties
        return {e.identifier for e in props['action'].enum_items}
    except Exception:
        return {'SELECT', 'DELETE_TRACK', 'DELETE_SEGMENTS'}


def _invoke_clean_tracks(context, *, used_error: float, action: str) -> None:
    """Ruft bpy.ops.clip.clean_tracks mit Param-Fallback ('clean_error' → 'error') im CLIP-Kontext auf."""
    area, region, space = _find_clip_window(context)
    if area and region and space:
        override = dict(area=area, region=region, space_data=space)
    else:
        override = {}

    # Erst versuchen wir 'clean_error', dann Fallback 'error'
    try:
        with context.temp_override(**override):
            bpy.ops.clip.clean_tracks(clean_error=float(used_error), action=str(action))
    except TypeError:
        with context.temp_override(**override):
            bpy.ops.clip.clean_tracks(error=float(used_error), action=str(action))


def _clean_tracks(context, *, used_error: float, action: str) -> Dict[str, int]:
    """
    Robustes Cleanup:
    - Unterstützt 'DISABLE' via Emulation: 'SELECT' → selektierte Tracks deaktivieren.
    - Für echte Actions ('SELECT'|'DELETE_TRACK'|'DELETE_SEGMENTS') ruft direkt den Operator.
    Gibt einfache Zählwerte zurück: {'selected': x, 'disabled': y}
    """
    allowed = _allowed_actions()
    clip = _active_clip(context)

    if action == "DISABLE":
        # 1) Selektieren lassen (über Operator)
        if "SELECT" not in allowed:
            raise TypeError("Operator supports no SELECT action for DISABLE emulation")
        _invoke_clean_tracks(context, used_error=used_error, action="SELECT")

        # 2) Selektierte deaktivieren
        selected = _count_selected(clip)
        disabled = 0
        for t in _iter_tracks(clip):
            try:
                if getattr(t, "select", False):
                    t.enabled = False
                    disabled += 1
            except Exception:
                pass

        # Optional: Selektion zurücksetzen
        _clear_selection(clip)

        return {"selected": selected, "disabled": disabled}

    # Normale Operator-Aktion
    op_action = action if action in allowed else "SELECT"
    _invoke_clean_tracks(context, used_error=used_error, action=op_action)
    selected = _count_selected(clip)
    return {"selected": selected, "disabled": 0}


# -----------------------------------------------------------------------------
# Öffentliche API
# -----------------------------------------------------------------------------

def run_projection_cleanup_builtin(
    context: bpy.types.Context,
    *,
    error_limit: float | None = None,
    threshold: float | None = None,
    max_error: float | None = None,
    wait_for_error: bool = True,
    wait_forever: bool = False,
    timeout_s: float = 20.0,
    action: str = "DELETE_TRACK",   # Default jetzt: direkt löschen
) -> Dict[str, Any]:
    """
    Führt Reprojection-Cleanup per bpy.ops.clip.clean_tracks aus.

    Ablauf:
      1) Error-Schwelle feststellen oder (optional) warten, bis Solve-Error lesbar.
      2) Operator ausführen: clean_tracks(clean_error=<used_error>, action=<action>).
         (Fallback-Parametername 'error' wird ebenfalls versucht.)
      3) Vorher/Nachher-Counts ermitteln und zurückgeben.
    """
    # 1) Schwelle bestimmen / warten
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
        return {"status": "SKIPPED", "reason": "no_error", "used_error": None, "action": action,
                "before": None, "after": None, "deleted": None, "selected": None, "disabled": None}

    # Wert vor Verwendung mit Faktor 1.25 multiplizieren
    used_error = float(used_error) * 1.25
    print(f"[Cleanup] Starte clean_tracks mit Grenzwert {used_error:.4f}px, action={action}")

    # 2) Vorher-Count, Operator aufrufen, Nachher-Count/Statistiken berechnen
    clip = _active_clip(context)
    before_count = _count_tracks(clip)

    try:
        stats = _clean_tracks(context, used_error=float(used_error), action=str(action))
    except Exception as ex:
        print(f"[Cleanup] Fehler bei clean_tracks: {ex!r}")
        return {"status": "ERROR", "reason": repr(ex), "used_error": used_error, "action": action,
                "before": before_count, "after": None, "deleted": None,
                "selected": None, "disabled": None}

    after_count = _count_tracks(clip)
    deleted = max(0, (before_count or 0) - (after_count or 0))
    selected = int(stats.get("selected", 0))
    disabled = int(stats.get("disabled", 0))

    print(f"[Cleanup] Cleanup abgeschlossen. Vorher={before_count}, nachher={after_count}, "
          f"entfernt={deleted}, selektiert={selected}, deaktiviert={disabled}")

    tco.on_projection_cleanup_finished(context=context)

    return {"status": "OK", "used_error": used_error, "action": action, "reason": None,
            "before": before_count, "after": after_count, "deleted": deleted,
            "selected": selected, "disabled": disabled}
