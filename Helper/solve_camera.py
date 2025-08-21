# Helper/solve_camera.py

from __future__ import annotations
import bpy

__all__ = (
    "solve_watch_clean",
    "run_solve_watch_clean",
)

# -------------------------- Kontext-/Helper-Funktionen ------------------------

def _find_clip_window(context):
    """Stellt einen gültigen CLIP_EDITOR-Kontext für Operator-Aufrufe sicher.
    Gibt (area, region_window, space) oder (None, None, None) zurück.
    """
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


# ------------------------------- Nur-Solve API --------------------------------

def solve_watch_clean(
    context,
    *,
    # Signatur beibehalten für Rückwärtskompatibilität – Parameter werden ignoriert
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    """
    Führt ausschließlich den Kamera-Solve aus – **ohne** Cleanup, **ohne**
    Persistenz in scene-Properties und **ohne** weitere Funktionsaufrufe.

    Rückgabe: {'FINISHED'} bei Erfolg, sonst {'CANCELLED'}
    """
    area, region, space = _find_clip_window(context)
    if not area or not space or not getattr(space, "clip", None):
        print("[SolveOnly] ERROR: Kein aktiver Movie Clip im CLIP_EDITOR gefunden.")
        return {'CANCELLED'}

    print("[SolveOnly] Starte Kamera-Solve …")
    try:
        with context.temp_override(area=area, region=region, space_data=space):
            res = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
    except Exception as e:
        print(f"[SolveOnly] ERROR: Solve-Aufruf fehlgeschlagen: {e}")
        return {'CANCELLED'}

    if res == {'FINISHED'}:
        print("[SolveOnly] Solve abgeschlossen.")
        return {'FINISHED'}

    print(f"[SolveOnly] Solve-Operator Rückgabe: {res} (nicht FINISHED)")
    return {'CANCELLED'}


def run_solve_watch_clean(
    context,
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    """Wrapper für direkten Funktionsaufruf.

    Beibehaltung der Signatur für Kompatibilität; Parameter werden ignoriert.
    """
    return solve_watch_clean(
        context,
        refine_limit_frames=int(refine_limit_frames),
        cleanup_factor=float(cleanup_factor),
        cleanup_mute_only=bool(cleanup_mute_only),
        cleanup_dry_run=bool(cleanup_dry_run),
    )
