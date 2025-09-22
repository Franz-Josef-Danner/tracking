import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only


class CLIP_OT_solve_camera_modal(Operator):
    bl_idname = "clip.solve_camera_modal"
    bl_label = "Solve Camera (Modal, einmal)"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _started: bool
    _result = None

    def _cleanup(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

    def invoke(self, context, event):
        wm = context.window_manager
        # Kleiner Timer, damit der Operator wirklich modal läuft und später erweiterbar ist
        self._timer = wm.event_timer_add(0.10, window=context.window)
        wm.modal_handler_add(self)
        self._started = False
        self._result = None
        return {"RUNNING_MODAL"}

    def execute(self, context):
        # Fallback: via Execute ebenfalls modal starten
        return self.invoke(context, None)

    def modal(self, context, event):
        # Nur auf Timer-Ticks reagieren
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}

        # Solve genau einmal starten
        if not getattr(self, "_started", False):
            self._started = True
            try:
                self._result = solve_camera_only(context)
            except Exception as exc:
                self._cleanup(context)
                self.report({"ERROR"}, f"Solve fehlgeschlagen: {exc}")
                return {"CANCELLED"}

            # Für jetzt: nach dem Auslösen direkt beenden.
            # (Spätere Erweiterungen können hier warten/prüfen.)
            self._cleanup(context)
            self.report({"INFO"}, f"Solve gestartet: {self._result}")
            return {"FINISHED"}

        return {"RUNNING_MODAL"}


def register():
    bpy.utils.register_class(CLIP_OT_solve_camera_modal)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_camera_modal)
