import bpy
from bpy.types import Operator
from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_solve_average_error, wait_for_solve_average_error, run_reduce_error_tracks


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

    def _find_low_and_jump_inline(self, context):
        """Mini-Flow: FindLow+Jump direkt ausführen (ohne Coordinator)."""
        try:
            # Wir verwenden den Operator, da er bereits Scene-State/Reports handhabt
            bpy.ops.clip.find_low_and_jump()
            self.report({'INFO'}, "FindLow+Jump ausgeführt (nach Reduce)")
        except Exception as exc:
            self.report({'WARNING'}, f"FindLow+Jump konnte nicht ausgeführt werden: {exc}")

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

            # Vergleich avg_error vs. Thresholds – warte kurz, damit Blender seine Logs zuerst schreibt
            scn = context.scene
            try:
                # Bis zu 3s auf stabilen avg_error warten
                avg_error = wait_for_solve_average_error(context, timeout=3.0, interval=0.05)
                if avg_error is None:
                    try:
                        avg_error = get_solve_average_error(context)
                    except Exception:
                        avg_error = None
                try:
                    thr = float(getattr(scn, "error_track", 2.0))
                except Exception:
                    thr = 2.0
                if avg_error is None:
                    print(f"[SolveSummary] avg_error=None threshold={float(thr):.3f} exceeds=False", flush=True)
                    self.report({'INFO'}, "Solve gestartet (avg_error unbekannt)")
                else:
                    ae = float(avg_error)
                    comp = ">" if ae > float(thr) else "<="
                    exceeds = ae > float(thr)
                    print(f"[SolveSummary] avg_error={ae:.3f} {comp} threshold={float(thr):.3f} exceeds={exceeds}", flush=True)
                    # Entscheidungslogik: 1) Wenn >10 → Reducer laufen lassen + direkt FindLow+Jump; 2) sonst wenn >error_track → (später weiterer Modal), aktuell nur Log
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
                        # Direkt zurück zu FIND: Low+Jump ausführen
                        self._find_low_and_jump_inline(context)
                    elif ae > float(thr):
                        print(f"[SolveDecision] avg_error ({ae:.3f}) > error_track ({float(thr):.3f}) → (next modal step TBD)", flush=True)
                    else:
                        self.report({'INFO'}, f"Solve: avg_error={ae:.3f} <= threshold={float(thr):.3f}")
            except Exception:
                # Logging darf nie den Flow brechen
                pass

            # Für jetzt: nach dem Auslösen direkt beenden.
            self._cleanup(context)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}


def register():
    bpy.utils.register_class(CLIP_OT_solve_camera_modal)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_camera_modal)
