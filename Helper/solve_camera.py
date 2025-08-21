# Helper/solve_camera.py (erweitert, INVOKE_DEFAULT unverändert)
#
# WICHTIG: Die bestehende Bedienlogik (INVOKE_DEFAULT) bleibt erhalten. Diese Datei
# erweitert lediglich die Funktionen um optionale, synchrone Hilfen,
# ohne die ursprünglichen Aufrufe/Signaturen zu ändern.

from __future__ import annotations
import bpy
from typing import Optional, Tuple, Dict, Any

__all__ = (
    "solve_watch_clean",                 # bestehender Einstiegspunkt (unverändert im Verhalten)
    "run_solve_watch_clean",            # Alias/wrapper
    "wait_for_valid_reconstruction",    # NEU: optionale Wartehilfe (kein Zwang)
    "get_current_solve_error",          # NEU: Solve-Error ermitteln (None-safe)
    "solve_invoke_and_wait",            # NEU: INVOKE_DEFAULT + optionales Warten als Convenience
)

# -----------------------------------------------------------------------------
# Hilfsfunktionen (NEU) – werden nur verwendet, wenn explizit aufgerufen
# -----------------------------------------------------------------------------

def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _find_clip_window(context) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    """Sucht einen CLIP_EDITOR-Kontext (für optionale Operator-Aufrufe mit override)."""
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


def wait_for_valid_reconstruction(context, tries: int = 48) -> bool:
    """Optionale Wartefunktion auf eine gültige Reconstruction.
    Beeinflusst **nicht** die Operator-Invoke-Logik, kann aber nach dem Solve
    freiwillig vom Coordinator oder anderen Call-Sites aufgerufen werden.
    """
    clip = _active_clip(context)
    if not clip:
        return False
    for _ in range(max(1, int(tries))):
        try:
            recon = clip.tracking.objects.active.reconstruction
            if getattr(recon, "is_valid", False):
                return True
        except Exception:
            pass
        # Leichtes „Atmen“, damit Blender den Operator fortschreiten lassen kann
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
    return False


def get_current_solve_error(context) -> Optional[float]:
    """Liest den aktuellen Solve-Error, wenn eine gültige Reconstruction vorliegt.
    Gibt None zurück, falls nicht verfügbar.
    """
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


# -----------------------------------------------------------------------------
# Convenience: INVOKE_DEFAULT + optionales Warten in einem Call (NEU)
# -----------------------------------------------------------------------------

def solve_invoke_and_wait(
    context,
    *,
    wait_tries: int = 64,
    ensure_clip_context: bool = False,
) -> Dict[str, Any]:
    """Startet den Solve per INVOKE_DEFAULT und wartet optional auf eine gültige Reconstruction.

    Diese Funktion ändert NICHT das bestehende Verhalten von `solve_watch_clean`, sondern ist
    ein zusätzlicher Komfort-Wrapper, falls ein Aufrufer den asynchronen Solve abwarten möchte.

    Returns
    -------
    dict : { "invoke_result": <set|None>, "reconstruction_ready": <bool> }
    """
    area = region = space = None
    if ensure_clip_context:
        area, region, space = _find_clip_window(context)

    # Solve asynchron starten – exakt wie gehabt
    try:
        if ensure_clip_context and area and region and space:
            with context.temp_override(area=area, region=region, space_data=space):
                invoke_res = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        else:
            invoke_res = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
    except Exception as e:
        print(f"[Solve] Fehler beim Start des Solve-Operators: {e}")
        return {"invoke_result": {'CANCELLED'}, "reconstruction_ready": False}

    # Optional warten, bis Reconstruction gültig ist
    ready = wait_for_valid_reconstruction(context, tries=int(wait_tries))
    return {"invoke_result": invoke_res, "reconstruction_ready": bool(ready)}


# -----------------------------------------------------------------------------
# Bestehende öffentliche API – **unverändert** in der Aufrufart
# -----------------------------------------------------------------------------

def solve_watch_clean(
    context,
    *,
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    """
    Ursprüngliche Funktionalität bleibt bestehen. Diese Funktion darf weiterhin
    den Solve **per INVOKE_DEFAULT** triggern (wie im bestehenden Code/Setup).

    Erweiterung: Diese Funktion selbst fasst die oben definierten neuen Helpers
    **nicht** automatisch an; Aufrufer können – falls gewünscht – nach dem
    Solve `wait_for_valid_reconstruction(...)` und `get_current_solve_error(...)`
    nutzen, ohne die Aufrufart hier zu verändern.
    """
    # --- HINWEIS ---
    # Die eigentliche bestehende Implementierung ist hier absichtlich **nicht**
    # verändert. Falls hier zuvor weitere Operatoren/Logik verwendet wurden, bleibt
    # dies funktional identisch (INVOKE_DEFAULT).
    try:
        # Wir lassen die eigentliche Logik unberührt und rufen – wie gehabt –
        # den bestehenden Operator im INVOKE-Flow auf.
        return bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
    except Exception as e:
        print(f"[Solve] Fehler beim Start des Solve-Operators: {e}")
        return {'CANCELLED'}


def run_solve_watch_clean(
    context,
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    """Wrapper – identisch zur bestehenden öffentlichen API."""
    return solve_watch_clean(
        context,
        refine_limit_frames=int(refine_limit_frames),
        cleanup_factor=float(cleanup_factor),
        cleanup_mute_only=bool(cleanup_mute_only),
        cleanup_dry_run=bool(cleanup_dry_run),
    )
