import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_avg_reprojection_error


def _safe_for_scene(obj):
    """Konvertiert Werte in Blender-ID-kompatible Typen (int/float/str/bool/list/dict)."""
    # Primitive
    if isinstance(obj, (int, float, str, bool)):
        return obj
    # None → String oder 0.0
    if obj is None:
        return "None"
    # Sets/Tuples/Listen → Liste
    if isinstance(obj, (set, tuple, list)):
        return [ _safe_for_scene(v) for v in list(obj) ]
    # Dict → rekursiv säubern, Keys zu String
    if isinstance(obj, dict):
        return { str(k): _safe_for_scene(v) for k, v in obj.items() }
    # Versuche float‑Cast
    try:
        return float(obj)
    except Exception:
        pass
    # Fallback: Stringrepräsentation
    try:
        return str(obj)
    except Exception:
        return "<unsupported>"


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
            try:
                scn["tco_last_solve_cycle"] = _safe_for_scene({"status": "ERROR", "reason": str(exc)})
            except Exception:
                pass
            return {'CANCELLED'}
        # 2. Reprojection Error abfragen
        try:
            avg_error = get_avg_reprojection_error(context)
        except Exception:
            avg_error = None
        # 3. Zusammenfassen (robust säubern)
        result = {
            "status": "OK",
            "score": score if isinstance(score, (int, float)) else _safe_for_scene(score),
            "avg_error": avg_error if isinstance(avg_error, (int, float)) else _safe_for_scene(avg_error),
        }
        try:
            scn["tco_last_solve_cycle"] = _safe_for_scene(result)
        except Exception:
            # Als Fallback einzelne Primitive setzen
            try:
                scn["tco_last_solve_status"] = str(result.get("status"))
            except Exception:
                pass
            try:
                scn["tco_last_solve_score"] = float(result.get("score") or 0.0)
            except Exception:
                pass
            try:
                ae = result.get("avg_error")
                scn["tco_last_solve_avg_error"] = float(ae) if isinstance(ae, (int, float)) else 0.0
            except Exception:
                pass
        self.report({'INFO'}, f"Solve-Cycle abgeschlossen: status=OK score={result['score']} avg_error={result['avg_error']}")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_solve_cycle)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_cycle)
