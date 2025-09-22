import bpy
from bpy.types import Operator
from typing import List, Dict, Any, Optional

# Helfer aus dem Projekt
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_solve_average_error, wait_for_solve_average_error

DISTORTION_MODELS: List[str] = ["POLYNOMIAL", "DIVISION", "BROWN"]  # NUKE ausgelassen


def _get_clip_and_camera(context):
    clip = (
        getattr(context, "edit_movieclip", None)
        or getattr(getattr(context, "space_data", None), "clip", None)
        or getattr(bpy.context, "edit_movieclip", None)
    )
    if not clip:
        try:
            clip = bpy.data.movieclips[0]
        except Exception:
            clip = None
    cam = getattr(getattr(getattr(clip, "tracking", None), "camera", None), "__class__", None)
    cam = clip.tracking.camera if clip and getattr(clip, "tracking", None) else None
    return clip, cam


def _solve_and_measure(context, timeout: float = 5.0) -> Optional[float]:
    try:
        solve_camera_only(context)
    except Exception:
        pass
    val = wait_for_solve_average_error(context, timeout=timeout, interval=0.05)
    if val is None:
        try:
            val = get_solve_average_error(context)
        except Exception:
            val = None
    return float(val) if isinstance(val, (int, float)) else None


class CLIP_OT_solve_test(Operator):
    bl_idname = "clip.solve_test"
    bl_label = "Solve Test (3 Models)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        clip, cam = _get_clip_and_camera(context)
        if not clip or not cam:
            self.report({'ERROR'}, "Kein Clip/Kamera gefunden")
            return {'CANCELLED'}

        orig_model = str(getattr(clip.tracking.camera, "distortion_model", "POLYNOMIAL"))
        results: List[Dict[str, Any]] = []

        for model in DISTORTION_MODELS:
            try:
                clip.tracking.camera.distortion_model = model
            except Exception:
                continue
            err = _solve_and_measure(context, timeout=5.0)
            results.append({"model": model, "avg_error": err})
            if err is None:
                self.report({'WARNING'}, f"Model {model}: kein gültiger Error")
            else:
                self.report({'INFO'}, f"Model {model}: avg_error={err:.4f}")

        # Besten wählen (kleinster gültiger Error)
        best = None
        try:
            valid = [r for r in results if isinstance(r.get("avg_error"), (int, float))]
            if valid:
                best = min(valid, key=lambda r: float(r["avg_error"]))
        except Exception:
            best = None

        if not best:
            # ursprüngliches Modell wiederherstellen
            try:
                clip.tracking.camera.distortion_model = orig_model
            except Exception:
                pass
            scn["tco_solve_test"] = {"status": "NO_VALID_RESULT", "results": results}
            self.report({'ERROR'}, "Kein gültiges Solve-Ergebnis erhalten")
            return {'CANCELLED'}

        # Bestes Modell fest setzen (kein finaler Solve hier)
        try:
            clip.tracking.camera.distortion_model = best["model"]
        except Exception:
            pass

        scn["tco_solve_test"] = {
            "status": "OK",
            "results": results,
            "best": {"model": best["model"], "avg_error": best["avg_error"]},
            "original_model": orig_model,
            "final_solve_performed": False,
        }
        self.report({'INFO'}, f"Bestes Model: {best['model']} (err={best['avg_error']:.4f if best['avg_error'] is not None else 'None'}) – finaler Solve ausgelassen")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_solve_test)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_test)
