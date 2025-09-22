import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_avg_reprojection_error

class CLIP_OT_track_cycle(Operator):
    bl_idname = "clip.track_cycle"
    bl_label = "Track Cycle (1x Solve)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        # 1. Kamera-Solve ausführen
        try:
            score = solve_camera_only(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Solve fehlgeschlagen: {exc}")
            scn["tco_last_solve_cycle"] = {"status": "ERROR", "reason": str(exc)}
            return {'CANCELLED'}
        # 2. Reprojection Error abfragen
        try:
            avg_error = get_avg_reprojection_error(context)
        except Exception:
            avg_error = None
        # 2b. Schwelle aus Szene lesen und vergleichen
        try:
            thr = float(getattr(scn, "error_track", 2.0))
        except Exception:
            thr = 2.0
        exceeds = (avg_error is not None) and (float(avg_error) > float(thr))
        # LOG: Vergleich ausgeben
        try:
            if avg_error is None:
                print(f"[SolveCheck] avg_error=None threshold={float(thr):.3f}")
            else:
                ae = float(avg_error)
                comp = ">" if ae > float(thr) else "<="
                print(f"[SolveCheck] avg_error={ae:.3f} {comp} threshold={float(thr):.3f} -> exceeds={ae > float(thr)}")
        except Exception:
            pass
        # 3. Zusammenfassen
        result = {
            "status": "OK",
            "score": score,
            "avg_error": avg_error,
            "error_threshold": thr,
            "exceeds_threshold": bool(exceeds),
        }
        scn["tco_last_solve_cycle"] = result
        # 4. Meldung
        if avg_error is None:
            self.report({'INFO'}, "Solve-Cycle abgeschlossen (avg_error unbekannt)")
        elif exceeds:
            self.report({'WARNING'}, f"Solve-Cycle: avg_error={float(avg_error):.3f} > threshold={float(thr):.3f}")
        else:
            self.report({'INFO'}, f"Solve-Cycle: avg_error={float(avg_error):.3f} <= threshold={float(thr):.3f}")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_track_cycle)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_track_cycle)
