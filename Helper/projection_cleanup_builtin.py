# Helper/projection_cleanup_builtin.py
from __future__ import annotations
"""
projection_cleanup_builtin.py — Cleanup mit optionalem Warten auf Solve-Error

Diese Datei wartet – falls gewünscht – solange, bis ein gültiger Solve-Error verfügbar ist
(oder bis ein Timeout erreicht ist). Optional kann auch endlos gewartet werden (wait_forever=True).
Danach kann ein Cleanup-Schritt erfolgen (Platzhalter – an eure Bedürfnisse anpassen).

Bestehende Kompatibilitätsfunktion:
- run_refine_on_high_error(...) bleibt als Alias erhalten.
"""

from typing import Optional, Tuple, Dict, Any
import bpy
import time

__all__ = ("run_projection_cleanup_builtin", "run_refine_on_high_error")


# -----------------------------------------------------------------------------
# Kontext- und Error-Utilities (kein Import aus solve_camera → Zyklus vermeiden)
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
    # Leichtes „Atmen“, damit Blender UI/Depsgraph weiterarbeiten kann
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


def _wait_until_error(context, *, wait_forever: bool, timeout_s: float, tick_s: float = 0.25) -> Optional[float]:
    """Wartet, bis ein gültiger Solve-Error verfügbar ist.
    - wait_forever=True  → endlos (UI kann blockieren!)
    - wait_forever=False → Timeout nach timeout_s Sekunden
    """
    deadline = time.monotonic() + float(timeout_s)
    n = 0
    while True:
        err = _get_current_solve_error_now(context)
        if err is not None:
            print(f"[CleanupWait] Solve-Error verfügbar: {err:.4f}px (after {n} ticks)")
            return err

        _poke_update()
        n += 1

        if not wait_forever and time.monotonic() >= deadline:
            print(f"[CleanupWait] Timeout nach {timeout_s:.1f}s – kein gültiger Error verfügbar.")
            return None

        # Kurze Pause; vermeidet 100% CPU
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
    # Mögliche Schwellenwert-Argumente (eins reicht; None → automatisch ermitteln)
    error_limit: float | None = None,
    threshold: float | None = None,
    max_error: float | None = None,
    # Warte-Parameter
    wait_for_error: bool = True,
    wait_forever: bool = False,
    timeout_s: float = 20.0,
) -> Dict[str, Any]:
    """
    Wartet optional auf einen gültigen Solve-Error und führt dann den Cleanup aus.
    Gibt ein Ergebnis-Dict zurück, inkl. 'used_error' (falls verfügbar).

    Achtung: wait_forever=True kann Blender blockieren (Endlosschleife)!
    """
    # 1) Fehlerwert bestimmen/abwarten
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
        return {"status": "SKIPPED", "reason": "no_error", "used_error": None}

    print(f"[Cleanup] Starte Cleanup mit Grenzwert {used_error:.4f}px")

    # 2) Hier eure eigentliche Cleanup-Logik einfügen:
    #    Beispiel: Marker mit sehr hohem reprojection error muten/löschen/etc.
    #    Der folgende Block ist absichtlich konservativ (kein zerstörerisches Verhalten).
    try:
        area, region, space = _find_clip_window(context)
        if area and space and getattr(space, "clip", None):
            with context.temp_override(area=area, region=region, space_data=space):
                # TODO: Ersetze dies durch eure echte Cleanup-Aktion.
                # Beispiel (Pseudo): bpy.ops.clip.filter_tracks(action='DELETE_TRACK', track_threshold=used_error)
                pass
    except Exception as ex:
        print(f"[Cleanup] Cleanup-Operator fehlgeschlagen: {ex!r}")
        return {"status": "ERROR", "reason": repr(ex), "used_error": used_error}

    print("[Cleanup] Cleanup abgeschlossen.")
    return {"status": "OK", "used_error": used_error}


# -----------------------------------------------------------------------------
# Abwärtskompatibler Name (wird im Coordinator als Fallback verwendet)
# -----------------------------------------------------------------------------

def run_refine_on_high_error(
    context: bpy.types.Context,
    *,
    max_error: float = 0.0,
    **_kw,
) -> Dict[str, Any]:
    """Alias zu run_projection_cleanup_builtin (Kompatibilität)."""
    return run_projection_cleanup_builtin(context, max_error=float(max_error), **_kw)
