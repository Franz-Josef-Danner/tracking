import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_avg_reprojection_error


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

            # Vergleich avg_error vs. error_track in die Konsole loggen
            scn = context.scene
            try:
                avg_error = None
                try:
                    # Kurzes Update, damit Reconstruction/Errors frisch sind
                    try:
                        context.view_layer.update()
                    except Exception:
                        pass
                    avg_error = get_avg_reprojection_error(context)
                except Exception:
                    avg_error = None
                try:
                    thr = float(getattr(scn, "error_track", 2.0))
                except Exception:
                    thr = 2.0
                if avg_error is None:
                    print(f"[SolveCheck] avg_error=None threshold={float(thr):.3f}")
                    self.report({'INFO'}, "Solve gestartet (avg_error unbekannt)")
                else:
                    ae = float(avg_error)
                    comp = ">" if ae > float(thr) else "<="
                    exceeds = ae > float(thr)
                    print(f"[SolveCheck] avg_error={ae:.3f} {comp} threshold={float(thr):.3f} -> exceeds={exceeds}")
                    if exceeds:
                        self.report({'WARNING'}, f"Solve: avg_error={ae:.3f} > threshold={float(thr):.3f}")
                    else:
                        self.report({'INFO'}, f"Solve: avg_error={ae:.3f} <= threshold={float(thr):.3f}")
            except Exception:
                # Logging darf nie den Flow brechen
                pass

            # Für jetzt: nach dem Auslösen direkt beenden.
            # (Spätere Erweiterungen können hier warten/prüfen.)
            self._cleanup(context)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}


def register():
    bpy.utils.register_class(CLIP_OT_solve_camera_modal)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_camera_modal)
