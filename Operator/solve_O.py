import bpy
import time
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_solve_average_error, run_reduce_error_tracks


class CLIP_OT_solve_camera_modal(Operator):
    bl_idname = "clip.solve_camera_modal"
    bl_label = "Solve Camera (Modal, einmal)"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _started: bool
    _result = None
    _waiting: bool
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
        self._started = False
        self._waiting = False
        self._result = None
        self._wait_deadline = time.perf_counter() + 10.0  # max 10s warten
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def _poll_avg_error(self, context):
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

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}

        # 1) Solve starten (einmalig)
        if not self._started:
            self._started = True
            try:
                self._result = solve_camera_only(context)
                # in den Wartemodus wechseln
                self._waiting = True
                self._wait_deadline = time.perf_counter() + 10.0
                return {"RUNNING_MODAL"}
            except Exception as exc:
                self._cleanup(context)
                self.report({"ERROR"}, f"Solve fehlgeschlagen: {exc}")
                return {"CANCELLED"}

        # 2) Auf gültigen avg_error warten (nicht-blockierend)
        if self._waiting:
            ae = self._poll_avg_error(context)
            if ae is None:
                if time.perf_counter() < self._wait_deadline:
                    return {"RUNNING_MODAL"}
                # Timeout → trotzdem fortfahren mit None
            else:
                # 3) Entscheidung / Aktionen
                scn = context.scene
                try:
                    thr = float(getattr(scn, "error_track", 2.0))
                except Exception:
                    thr = 2.0
                comp = ">" if ae > thr else "<="
                print(f"[SolveSummary] avg_error={ae:.3f} {comp} threshold={thr:.3f} exceeds={ae > thr}", flush=True)
                if ae > 10.0 and run_reduce_error_tracks is not None:
                    old_thr = scn.get("error_track", None)
                    try:
                        scn["error_track"] = 10.0
                    except Exception:
                        pass
                    try:
                        res_red = run_reduce_error_tracks(context)
                        try:
                            scn["tco_last_reduce_error_tracks"] = res_red
                        except Exception:
                            pass
                        self.report({'INFO'}, f"Reduce-Error-Tracks ausgeführt (thr=10): deleted={int(res_red.get('deleted',0))}")
                        print(f"[SolveDecision] Reducer executed: deleted={int(res_red.get('deleted',0))}", flush=True)
                    except Exception as _rex:
                        self.report({'WARNING'}, f"Reduce-Error-Tracks Fehler: {_rex}")
                    finally:
                        try:
                            if old_thr is None:
                                del scn["error_track"]
                            else:
                                scn["error_track"] = old_thr
                        except Exception:
                            pass
                elif ae > thr:
                    print(f"[SolveDecision] avg_error ({ae:.3f}) > error_track ({thr:.3f}) → (next modal step TBD)", flush=True)
                else:
                    self.report({'INFO'}, f"Solve: avg_error={ae:.3f} <= threshold={thr:.3f}")

                # Abschluss
                self._waiting = False
                self._cleanup(context)
                return {"FINISHED"}

            # Keine Entscheidung möglich (None + Timeout noch nicht erreicht)
            return {"RUNNING_MODAL"}

        # Fallback
        self._cleanup(context)
        return {"FINISHED"}


def register():
    bpy.utils.register_class(CLIP_OT_solve_camera_modal)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_camera_modal)
