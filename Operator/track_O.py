import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_avg_reprojection_error

class CLIP_OT_solve_cycle(Operator):
    bl_idname = "clip.solve_cycle"
    bl_label = "Solve Cycle (1x Solve)"
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
        # 3. Zusammenfassen
        result = {
            "status": "OK",
            "score": score,
            "avg_error": avg_error,
        }
        scn["tco_last_solve_cycle"] = result
        self.report({'INFO'}, f"Solve-Cycle abgeschlossen: {result}")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_solve_cycle)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_cycle)
