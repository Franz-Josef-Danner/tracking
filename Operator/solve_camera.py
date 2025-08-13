# solve_camera.py
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
        # Vorbedingungen
        clip, recon = _get_reconstruction(context)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Movie Clip.")
            return {'CANCELLED'}

        # 1) Solve-Error persistieren (wie gehabt)
        scene = context.scene
        scene["solve_error"] = float(avg2)
        print(f"[SolveWatch] Persistiert: scene['solve_error'] = {avg2:.6f}")
        
        # 2) Projection-Cleanup konfigurieren
        #    Option A: Szene-Threshold (empfohlen)
        threshold_key = "error_track"  # typ. 2.0 px
        
        #    Option B (optional): Solve-Error nutzen, aber auf sinnvolle Größenordnung clampen
        # cleanup_use_solve_error = False
        # if cleanup_use_solve_error:
        #     scene["solve_error_clamped"] = min(float(scene.get("solve_error", 3.0)), 5.0)
        #     threshold_key = "solve_error_clamped"
        
        cleanup_factor = float(getattr(self, "cleanup_factor", 1.0))           # 1.0–1.5 üblich
        cleanup_frames = int(getattr(self, "cleanup_frames", 0))               # 0 = keine Mindestlänge
        cleanup_action = 'DELETE_TRACK' if not getattr(self, "cleanup_mute_only", False) else 'SELECT'
        cleanup_dryrun = bool(getattr(self, "cleanup_dry_run", False))
        
        print(f"[SolveWatch] Starte Projection-Cleanup (builtin clip.clean_tracks): key={threshold_key}, factor={cleanup_factor}, frames={cleanup_frames}, action={cleanup_action}, dry_run={cleanup_dryrun}")
        
        try:
            # 3) Built-in Cleanup ausführen
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
        
        print(f"[SolveWatch] Projection-Cleanup abgeschlossen: affected={int(report['affected'])}, threshold={report['threshold']:.6f}, mode={report['action']}")
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
