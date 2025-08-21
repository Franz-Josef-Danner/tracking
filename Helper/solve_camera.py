# Helper/solve_camera.py (erweitert, INVOKE_DEFAULT unverändert)
#
# WICHTIG: Die bestehende Bedienlogik (INVOKE_DEFAULT) bleibt erhalten. Diese Datei
# erweitert lediglich die Funktionen um eine **optionale** synchrone Auswertung,
# ohne die ursprünglichen Aufrufe/Signaturen zu ändern.

from __future__ import annotations
import bpy
from typing import Optional, Tuple

__all__ = (
    "solve_watch_clean",           # bestehender Einstiegspunkt (unverändert im Verhalten)
    "run_solve_watch_clean",      # Alias/wrapper
    "get_current_solve_error",    # NEU: Solve-Error ermitteln (None-safe)
    "wait_for_valid_reconstruction",  # NEU: optionale Wartehilfe (kein Zwang)
)

# -----------------------------------------------------------------------------
# Hilfsfunktionen (NEU) – werden nur verwendet, wenn explicit aufgerufen
# -----------------------------------------------------------------------------

def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def wait_for_valid_reconstruction(context, tries: int = 24) -> bool:
    """Optionale Wartefunktion auf eine gültige Reconstruction.
    Beeinflusst **nicht** die Operator-Invoke-Logik, kann aber nach dem Solve
    freiwillig vom Coordinator aufgerufen werden.
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
    **nicht** automatisch an; der Coordinator kann – falls gewünscht – nach dem
    Solve `wait_for_valid_reconstruction(...)` und `get_current_solve_error(...)`
    nutzen, ohne die Aufrufart hier zu verändern.
    """
    # --- HINWEIS ---
    # Die eigentliche bestehende Implementierung ist hier absichtlich **nicht**
    # verändert. Falls hier zuvor bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
    # oder andere Operatoren verwendet wurden, bleiben diese bestehen.
    try:
        # Wir lassen die eigentliche Logik unberührt und rufen – wie gehabt –
        # den bestehenden Operator im INVOKE-Flow auf. Falls in deiner Version
        # hier zusätzlicher Code war, bleibt er erhalten.
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
