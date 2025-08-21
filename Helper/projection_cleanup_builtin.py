# Helper/projection_cleanup_builtin.py
from __future__ import annotations
"""
projection_cleanup_builtin.py — Reprojection-Cleanup mit optionalem Warten auf Solve-Error

- Kein run_refine_on_high_error mehr.
- Einziger Einstiegspunkt: run_projection_cleanup_builtin(...).
- Wartet optional, bis ein gültiger Solve-Error verfügbar ist (oder Timeout),
  und führt dann bpy.ops.clip.clean_tracks mit clean_error=<used_error> aus.

Hinweis:
- Der Operator-Parameter heißt in gängigen Blender-Versionen 'clean_error'.
  Für Kompatibilität probieren wir auch 'error' als Fallback.
"""

from typing import Optional, Tuple, Dict, Any
import bpy
import time

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
# Öffentliche API
# -----------------------------------------------------------------------------

def run_projection_cleanup_builtin(
    context: bpy.types.Context,
    *,
    # Einer dieser Werte (wenn gesetzt) wird als Schwellwert verwendet;
    # wenn keiner gesetzt ist, kann gewartet werden, bis ein Error verfügbar ist.
    error_limit: float | None = None,
    threshold: float | None = None,
    max_error: float | None = None,

    # Warte-Optionen
    wait_for_error: bool = True,
    wait_forever: bool = False,
    timeout_s: float = 20.0,

    # Cleanup-Optionen
    action: str = "DISABLE",   # 'DISABLE', 'DELETE_TRACK', 'DELETE_SEGMENTS', 'SELECT'
) -> Dict[str, Any]:
    """
    Führt Reprojection-Cleanup per bpy.ops.clip.clean_tracks aus.

    Ablauf:
      1) Error-Schwelle feststellen oder (optional) warten, bis Solve-Error lesbar.
      2) Operator ausführen: clean_tracks(clean_error=<used_error>, action=<action>).
         (Fallback-Parametername 'error' wird ebenfalls versucht.)

    Rückgabe:
      dict(status='OK'|'SKIPPED'|'ERROR', used_error=float|None, action=str, reason=str|None)
    """
    # 1) Schwelle bestimmen / warten
    used_error = None
    for val in (error_limit, threshold, max_error):
        if val is not None:
            used_error = float(val)
            break

    if used_error is None and wait_for_error:
        print("[Cleanup] Kein Error übergeben → warte auf Solve-Error …")
        used_error = _wait_until_error(context, wait_forever=bool(wait_forever), timeout_s=float(timeout_s))

    if used_error is None:
        print("[Cleanup] Kein gültiger Solve-Error verfügbar – Cleanup wird SKIPPED.")
        return {"status": "SKIPPED", "reason": "no_error", "used_error": None, "action": action}

    print(f"[Cleanup] Starte clean_tracks mit Grenzwert {used_error:.4f}px, action={action}")

    # 2) Operator ausführen (Kontext-Override für CLIP_EDITOR)
    try:
        area, region, space = _find_clip_window(context)
        if not (area and region and space and getattr(space, "clip", None)):
            print("[Cleanup] Kein CLIP_EDITOR-Kontext gefunden – versuche ohne Override.")

            # Erst mit 'clean_error', dann Fallback 'error'
            try:
                bpy.ops.clip.clean_tracks(clean_error=float(used_error), action=str(action))
            except TypeError:
                bpy.ops.clip.clean_tracks(error=float(used_error), action=str(action))
        else:
            with context.temp_override(area=area, region=region, space_data=space):
                try:
                    bpy.ops.clip.clean_tracks(clean_error=float(used_error), action=str(action))
                except TypeError:
                    bpy.ops.clip.clean_tracks(error=float(used_error), action=str(action))
    except Exception as ex:
        print(f"[Cleanup] Fehler bei clean_tracks: {ex!r}")
        return {"status": "ERROR", "reason": repr(ex), "used_error": used_error, "action": action}

    print("[Cleanup] Cleanup abgeschlossen.")
    return {"status": "OK", "used_error": used_error, "action": action}
