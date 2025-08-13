import bpy
from bpy.types import Operator
from bpy.props import IntProperty, FloatProperty, BoolProperty

# Sicherstellen, dass der Refine-Operator-Klasse geladen ist (liegt in Helper/)
# (Registrierung erfolgt zentral in deinem Addon-__init__ bzw. Operator/__init__)
from ..Helper.refine_high_error import run_refine_on_high_error
from ..Helper.projection_cleanup_builtin import builtin_projection_cleanup, find_clip_window


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
    """Startet Solve synchron, liefert average_error (oder 0.0)."""
    area, region, space = _find_clip_window(context)
    if not area:
        raise RuntimeError("Kein CLIP_EDITOR-Fenster gefunden (Kontext erforderlich).")

    with context.temp_override(area=area, region=region, space_data=space):
        res = bpy.ops.clip.solve_camera('EXEC_DEFAULT')
        if res != {'FINISHED'}:
            raise RuntimeError("Solve fehlgeschlagen oder abgebrochen.")

    _, recon = _get_reconstruction(context)
    avg = float(getattr(recon, "average_error", 0.0)) if (recon and recon.is_valid) else 0.0
    print(f"[SolveWatch] Solve {label or ''} OK (AvgErr={avg:.6f}).")
    return avg


# ------------------------------- Orchestrator --------------------------------

class CLIP_OT_solve_watch_clean(Operator):
    """
    Orchestriert:
      1) Solve
      2) Refine (Top-N per scene['marker_basis'])
      3) Solve
      4) Wenn AvgErr >= scene['error_track']: scene['solve_error']=AvgErr setzen und
         CLIP_OT_clean_tracks_by_projection_error ausführen.
    """
    bl_idname = "clip.solve_watch_clean"
    bl_label  = "Solve → Refine (Top-N) → Solve → Clean (Projection Error)"
    bl_options = {'REGISTER', 'UNDO'}

    # Optionales Cap für die Refine-Menge (≤ Top-N)
    refine_limit_frames: IntProperty(
        name="Refine Cap",
        description="Optionale Obergrenze der zu refinenden Frames (0 = kein Cap)",
        default=0, min=0
    )

    # Parameter für Projection-Cleanup
    cleanup_factor: FloatProperty(
        name="Cleanup-Faktor",
        description="Multiplikator auf scene['solve_error'] für den Projection-Cleanup",
        default=1.0, min=0.0, soft_min=0.5, soft_max=3.0
    )
    cleanup_mute_only: BoolProperty(
        name="Nur muten (nicht löschen)",
        default=False
    )
    cleanup_dry_run: BoolProperty(
        name="Dry Run (nur Log)",
        default=False
    )

    @classmethod
    def poll(cls, context):
        return _get_active_clip(context) is not None

    def execute(self, context):
        from ..Helper.projection_cleanup_builtin import builtin_projection_cleanup, find_clip_window
    
        scene = context.scene
    
        # --- 0) Clip-Kontext sicherstellen ---
        area, region, space = find_clip_window(context)
        if not area or not space or not getattr(space, "clip", None):
            self.report({'ERROR'}, "Kein aktiver Movie Clip im CLIP_EDITOR gefunden.")
            return {'CANCELLED'}
        clip = space.clip
    
        # --- 1) Kamera-Solve ausführen ---
        print("[SolveWatch] Starte Kamera-Solve …")
        with context.temp_override(area=area, region=region, space_data=space):
            try:
                res = bpy.ops.clip.solve_camera()
            except Exception as e:
                self.report({'ERROR'}, f"Solve-Aufruf fehlgeschlagen: {e}")
                return {'CANCELLED'}
        print(f"[SolveWatch] Solve-Operator Rückgabe: {res}")
    
        # --- 2) Solve-Error sicher auslesen ---
        avg2 = None
        try:
            # Aktives Tracking-Objekt → Reconstruction
            tracking = clip.tracking
            obj = tracking.objects.active if tracking.objects else None
            recon = obj.reconstruction if obj else None
            if recon and getattr(recon, "is_valid", False):
                avg2 = float(getattr(recon, "average_error", 0.0))
        except Exception as e:
            print(f"[SolveWatch] WARN: Konnte Solve-Error nicht lesen: {e}")
    
        if avg2 is None:
            self.report({'ERROR'}, "Solve-Error konnte nicht ermittelt werden (Reconstruction ungültig).")
            return {'CANCELLED'}
    
        print(f"[SolveWatch] Solve OK (AvgErr={avg2:.6f}).")
    
        # --- 3) Persistieren + Schwellen steuern ---
        scene["solve_error"] = float(avg2)
        print(f"[SolveWatch] Persistiert: scene['solve_error'] = {avg2:.6f}")
    
        # Standard: szenischer Track-Threshold (Pixel) verwenden
        error_track = float(scene.get("error_track", 2.0))
        threshold_key = "error_track"
        cleanup_factor = float(getattr(self, "cleanup_factor", 1.0))
        cleanup_frames = int(getattr(self, "cleanup_frames", 0))
        cleanup_dryrun = bool(getattr(self, "cleanup_dry_run", False))
        cleanup_action = 'SELECT' if bool(getattr(self, "cleanup_mute_only", False)) else 'DELETE_TRACK'
    
        print(f"[SolveWatch] Starte Projection-Cleanup (builtin): key={threshold_key}, "
              f"factor={cleanup_factor}, frames={cleanup_frames}, action={cleanup_action}, dry_run={cleanup_dryrun}")
    
        # --- 4) Built-in Cleanup ausführen ---
        try:
            report = builtin_projection_cleanup(
                context,
                error_key=threshold_key,
                factor=cleanup_factor,
                frames=cleanup_frames,
                action=cleanup_action,
                dry_run=cleanup_dryrun,
            )
        except Exception as e:
            self.report({'ERROR'}, f"Projection-Cleanup fehlgeschlagen: {e}")
            return {'CANCELLED'}
    
        for line in report.get("log", []):
            print(line)
    
        print(f"[SolveWatch] Projection-Cleanup abgeschlossen: "
              f"affected={int(report.get('affected', 0))}, "
              f"threshold={float(report.get('threshold', error_track)):.6f}, "
              f"mode={report.get('action', cleanup_action)}")
    
        self.report({'INFO'}, f"Cleanup getriggert (AvgErr={avg2:.6f} ≥ error_track={error_track:.6f}).")
        return {'FINISHED'}





# -------------- Convenience-Wrapper (für Aufrufe aus __init__.py etc.) -------

def run_solve_watch_clean(
    context,
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    area, region, space = _find_clip_window(context)
    if not area:
        raise RuntimeError("Kein CLIP_EDITOR-Fenster gefunden (Kontext erforderlich).")
    with context.temp_override(area=area, region=region, space_data=space):
        return bpy.ops.clip.solve_watch_clean(
            'EXEC_DEFAULT',
            refine_limit_frames=int(refine_limit_frames),
            cleanup_factor=float(cleanup_factor),
            cleanup_mute_only=bool(cleanup_mute_only),
            cleanup_dry_run=bool(cleanup_dry_run),
        )


# -------------------------------- Register -----------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_solve_watch_clean)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_watch_clean)
