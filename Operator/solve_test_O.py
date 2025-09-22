import bpy
import time
from bpy.types import Operator
from typing import List, Dict, Any, Optional

# Helfer aus dem Projekt
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_solve_average_error

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
    cam = clip.tracking.camera if clip and getattr(clip, "tracking", None) else None
    return clip, cam


class CLIP_OT_solve_test(Operator):
    bl_idname = "clip.solve_test"
    bl_label = "Solve Test (3 Models)"
    bl_options = {"REGISTER", "UNDO"}

    # Runtime
    _timer = None
    _idx: int
    _models: List[str]
    _results: List[Dict[str, Any]]
    _orig_model: str
    _phase: str  # "SOLVE" | "WAIT"
    _wait_deadline: float

    def _cleanup(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.10, window=context.window)
        wm.modal_handler_add(self)
        self._models = list(DISTORTION_MODELS)
        self._idx = 0
        self._results = []
        clip, cam = _get_clip_and_camera(context)
        self._orig_model = str(getattr(getattr(clip, 'tracking', None), 'camera', None).distortion_model) if clip and getattr(clip, 'tracking', None) else 'POLYNOMIAL'
        self._phase = "SOLVE"
        self._wait_deadline = 0.0
        # optional Flag
        try:
            context.scene["tco_solve_test_active"] = True
        except Exception:
            pass
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def _set_model(self, context, model: str) -> bool:
        clip, cam = _get_clip_and_camera(context)
        if not clip or not cam:
            return False
        try:
            clip.tracking.camera.distortion_model = model
            return True
        except Exception:
            return False

    def _poll_avg_error(self, context) -> Optional[float]:
        try:
            try:
                context.view_layer.update()
            except Exception:
                pass
            val = get_solve_average_error(context)
            if isinstance(val, (int, float)):
                return float(val)
        except Exception:
            pass
        return None

    def _finish(self, context):
        clip, cam = _get_clip_and_camera(context)
        best = None
        try:
            valid = [r for r in self._results if isinstance(r.get("avg_error"), (int, float))]
            if valid:
                best = min(valid, key=lambda r: float(r["avg_error"]))
        except Exception:
            best = None
        # Bestes Modell fest setzen (kein finaler Solve hier)
        try:
            if clip and getattr(clip, 'tracking', None):
                clip.tracking.camera.distortion_model = (best["model"] if best else self._orig_model)
        except Exception:
            pass
        payload = {
            "status": "OK" if best else "NO_VALID_RESULT",
            "results": self._results,
            "best": ({"model": best["model"], "avg_error": best["avg_error"]} if best else None),
            "original_model": self._orig_model,
            "final_solve_performed": False,
        }
        try:
            context.scene["tco_solve_test"] = payload
            context.scene["tco_solve_test_active"] = False
        except Exception:
            pass
        if best:
            self.report({'INFO'}, f"Bestes Model: {best['model']} (err={best['avg_error']:.4f}) – finaler Solve ausgelassen")
        else:
            self.report({'WARNING'}, "Solve-Test: kein gültiges Ergebnis – Modell unverändert")
        self._cleanup(context)
        return {"FINISHED"}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {"RUNNING_MODAL"}

        # abgeschlossen?
        if self._idx >= len(self._models):
            return self._finish(context)

        model = self._models[self._idx]

        # Phase 1: Solve anstoßen
        if self._phase == "SOLVE":
            ok = self._set_model(context, model)
            if not ok:
                self._results.append({"model": model, "avg_error": None, "status": "SET_MODEL_FAILED"})
                self._idx += 1
                self._phase = "SOLVE"
                return {"RUNNING_MODAL"}
            try:
                solve_camera_only(context)
            except Exception:
                pass
            self._wait_deadline = time.perf_counter() + 10.0
            self._phase = "WAIT"
            return {"RUNNING_MODAL"}

        # Phase 2: Auf Error warten (nicht blockierend)
        if self._phase == "WAIT":
            ae = self._poll_avg_error(context)
            if ae is None and time.perf_counter() < self._wait_deadline:
                return {"RUNNING_MODAL"}
            # Ergebnis eintragen (None bei Timeout)
            self._results.append({"model": model, "avg_error": (float(ae) if isinstance(ae, (int, float)) else None)})
            if ae is None:
                self.report({'WARNING'}, f"Model {model}: kein gültiger Error")
            else:
                self.report({'INFO'}, f"Model {model}: avg_error={float(ae):.4f}")
            self._idx += 1
            self._phase = "SOLVE"
            return {"RUNNING_MODAL"}

        # Fallback
        return {"RUNNING_MODAL"}


def register():
    bpy.utils.register_class(CLIP_OT_solve_test)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_test)
