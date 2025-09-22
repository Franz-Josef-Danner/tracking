import bpy
from bpy.types import Operator
from typing import List

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


def _next_model(current: str) -> str:
    try:
        idx = DISTORTION_MODELS.index(str(current))
    except Exception:
        idx = 0
    return DISTORTION_MODELS[(idx + 1) % len(DISTORTION_MODELS)]


class CLIP_OT_solve_test(Operator):
    bl_idname = "clip.solve_test"
    bl_label = "Solve Test (Next Model)"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None

    def _cleanup(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        try:
            context.scene["tco_solve_test_active"] = True
        except Exception:
            pass
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {"RUNNING_MODAL"}
        clip, cam = _get_clip_and_camera(context)
        if not clip or not cam:
            try:
                context.scene["tco_solve_test"] = {"status": "NO_CLIP_OR_CAMERA"}
                context.scene["tco_solve_test_active"] = False
            except Exception:
                pass
            self.report({'WARNING'}, "Solve-Test: kein Clip/Kamera – Modell unverändert")
            self._cleanup(context)
            return {"FINISHED"}
        current = str(getattr(clip.tracking.camera, "distortion_model", "POLYNOMIAL"))
        nxt = _next_model(current)
        try:
            clip.tracking.camera.distortion_model = nxt
            self.report({'INFO'}, f"Solve-Test: Model gewechselt {current} → {nxt}")
        except Exception as exc:
            self.report({'WARNING'}, f"Solve-Test: Modelwechsel fehlgeschlagen: {exc}")
        # Flags/Payload
        try:
            context.scene["tco_solve_test"] = {"status": "OK", "previous": current, "next": nxt}
            context.scene["tco_solve_test_active"] = False
        except Exception:
            pass
        self._cleanup(context)
        return {"FINISHED"}


def register():
    bpy.utils.register_class(CLIP_OT_solve_test)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_test)
