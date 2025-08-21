# Helper/solve_camera.py

from __future__ import annotations
import bpy

# Sicherstellen, dass der Refine-Helper geladen ist (liegt in Helper/)
from .refine_high_error import run_refine_on_high_error  # noqa: F401 (import beibehalten, keine Funktionsänderung)
from .projection_cleanup_builtin import find_clip_window  # nur für Kontext, kein direkter Cleanup mehr

__all__ = (
    "solve_watch_clean",
    "run_solve_watch_clean",
)

# POST-CLEAN Signal-Keys (vom Coordinator ausgewertet)
_POST_REQ_KEY = "__post_cleanup_request"
_POST_THR_KEY = "__post_cleanup_threshold"

# -------------------------- Kontext-/Helper-Funktionen ------------------------

def _find_clip_window(context):
    """Sichert einen gültigen CLIP_EDITOR-Kontext für Operator-Aufrufe."""
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


def _get_active_clip(context):
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _get_reconstruction(context):
    clip = _get_active_clip(context)
    if not clip:
        return None, None
    obj = clip.tracking.objects.active
    return clip, obj.reconstruction


def _solve_once(context, *, label: str = "") -> float:
    """Startet Solve synchron per Operator, liefert average_error (oder 0.0)."""
    area, region, space = _find_clip_window(context)
    if not area:
        raise RuntimeError("Kein CLIP_EDITOR-Fenster gefunden (Kontext erforderlich).")

    with context.temp_override(area=area, region=region, space_data=space):
        res = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        if res != {'FINISHED'}:
            raise RuntimeError("Solve fehlgeschlagen oder abgebrochen.")

    _, recon = _get_reconstruction(context)
    avg = float(getattr(recon, "average_error", 0.0)) if (recon and recon.is_valid) else 0.0
    print(f"[SolveWatch] Solve {label or ''} OK (AvgErr={avg:.6f}).")
    return avg


# ------------------------------- Orchestrator --------------------------------

def solve_watch_clean(
    context,
    *,
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,      # ungenutzt (Cleanup im Coordinator)
    cleanup_mute_only: bool = False,  # ungenutzt
    cleanup_dry_run: bool = False,    # ungenutzt
):
    """
    Orchestriert:
      1) Solve (Operator via INVOKE_DEFAULT)
      2) Solve-Error lesen und in scene['solve_error'] persistieren
      3) **Signal an Coordinator** setzen, WENN AvgErr ≥ scene['error_track'].
         (Coordinator führt dann Projection-Cleanup mit genau diesem AvgErr aus.)
    """
    scene = context.scene

    # --- 0) Clip-Kontext sicherstellen ---
    area, region, space = find_clip_window(context)
    if not area or not space or not getattr(space, "clip", None):
        print("[SolveWatch] ERROR: Kein aktiver Movie Clip im CLIP_EDITOR gefunden.")
        return {'CANCELLED'}
    clip = space.clip

    # --- 1) Kamera-Solve ausführen ---
    print("[SolveWatch] Starte Kamera-Solve …")
    with context.temp_override(area=area, region=region, space_data=space):
        try:
            res = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        except Exception as e:
            print(f"[SolveWatch] ERROR: Solve-Aufruf fehlgeschlagen: {e}")
            return {'CANCELLED'}
    print(f"[SolveWatch] Solve-Operator Rückgabe: {res}")

    # --- 2) Solve-Error sicher auslesen ---
    avg = None
    try:
        tracking = clip.tracking
        obj = tracking.objects.active if tracking.objects else None
        recon = obj.reconstruction if obj else None
        if recon and getattr(recon, "is_valid", False):
            avg = float(getattr(recon, "average_error", 0.0))
    except Exception as e:
        print(f"[SolveWatch] WARN: Konnte Solve-Error nicht lesen: {e}")

    if avg is None:
        print("[SolveWatch] ERROR: Solve-Error konnte nicht ermittelt werden (Reconstruction ungültig).")
        return {'CANCELLED'}

    print(f"[SolveWatch] Solve OK (AvgErr={avg:.6f}).")

    # --- 3) Persistieren ---
    scene["solve_error"] = float(avg)
    print(f"[SolveWatch] Persistiert: scene['solve_error'] = {avg:.6f}")

    # --- 4) Signal setzen, wenn AvgErr >= error_track ---
    current_thr = float(scene.get("error_track", 2.0))
    if float(avg) >= current_thr:
        scene[_POST_THR_KEY] = float(avg)
        scene[_POST_REQ_KEY] = True
        print(f"[SolveWatch] POST-CLEAN Signal gesetzt (thr={avg:.6f} ≥ error_track={current_thr:.6f}).")
    else:
        print(f"[SolveWatch] Kein POST-CLEAN: AvgErr({avg:.6f}) < error_track({current_thr:.6f}).")

    return {'FINISHED'}


# -------------- Convenience-Wrapper -----------------------------------------

def run_solve_watch_clean(
    context,
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    """Identisches Verhalten wie solve_watch_clean, aber ohne separaten Operator-Dispatch."""
    area, region, space = _find_clip_window(context)
    if not area:
        raise RuntimeError("Kein CLIP_EDITOR-Fenster gefunden (Kontext erforderlich).")
    with context.temp_override(area=area, region=region, space_data=space):
        return solve_watch_clean(
            context,
            refine_limit_frames=int(refine_limit_frames),
            cleanup_factor=float(cleanup_factor),
            cleanup_mute_only=bool(cleanup_mute_only),
            cleanup_dry_run=bool(cleanup_dry_run),
        )
