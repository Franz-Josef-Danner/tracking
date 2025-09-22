import bpy
from bpy.types import Operator

# Optionaler Direktimport für Fallback (Bootstrap)
try:
    from .bootstrap_O import CLIP_OT_bootstrap_cycle  # type: ignore
except Exception:
    CLIP_OT_bootstrap_cycle = None  # type: ignore

# Optional: Bidirectional-Track aus Helper registrieren/nutzen
try:
    from ..Helper.bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
except Exception:
    try:
        from .bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
    except Exception:
        CLIP_OT_bidirectional_track = None  # type: ignore

# Solve‑Error Abfrage (Reduce jetzt in solve_clean_O)
try:
    from ..Helper.reduce_error_tracks import wait_for_solve_average_error, get_solve_average_error  # type: ignore
except Exception:
    def wait_for_solve_average_error(context, timeout=None, interval=0.05):  # type: ignore
        return None
    def get_solve_average_error(context):  # type: ignore
        return None

__all__ = ("CLIP_OT_camera_tracking_coordinator",)


class CLIP_OT_camera_tracking_coordinator(Operator):
    """Modaler Ablauf: FIND → DETECT → TRACK; Wenn nichts zu finden: Clean → Solve → ggf. Solve-Test → Refine-Solve → zurück zu FIND bei Reduce."""

    bl_idname = "clip.camera_tracking_coordinator"
    bl_label = "Camera Tracking Coordinator"
    bl_options = {"REGISTER", "UNDO"}

    # Runtime‑State
    _timer: object | None = None
    phase: str = "FIND"
    detect_started: bool = False
    track_started: bool = False

    def _finish(self, context, msg: str = "", cancel: bool = False):
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None
        if msg:
            self.report({'WARNING' if cancel else 'INFO'}, msg)
        return {'CANCELLED' if cancel else 'FINISHED'}

    def execute(self, context):
        # 1) Bootstrap immer zuerst ausführen
        try:
            bpy.ops.clip.bootstrap_cycle()
            self.report({'INFO'}, "Bootstrap ausgeführt (via bpy.ops)")
        except Exception as exc:
            # Fallback: direkter Klassenaufruf
            try:
                if CLIP_OT_bootstrap_cycle is not None:
                    try:
                        bpy.utils.register_class(CLIP_OT_bootstrap_cycle)
                    except Exception:
                        pass
                    op = CLIP_OT_bootstrap_cycle()
                    op.execute(context)
                    self.report({'INFO'}, "Bootstrap ausgeführt (direkter Fallback)")
                else:
                    self.report({'WARNING'}, f"Bootstrap konnte nicht über bpy.ops gestartet werden ({exc}) und Fallback ist nicht verfügbar.")
            except Exception as exc2:
                self.report({'WARNING'}, f"Bootstrap-Fallback fehlgeschlagen: {exc2}")

        # 2) Modal‑Loop initialisieren
        self.phase = "FIND"
        self.detect_started = False
        self.track_started = False
        wm = context.window_manager
        win = getattr(context, "window", None) or getattr(bpy.context, "window", None)
        try:
            self._timer = wm.event_timer_add(0.10, window=win) if win else wm.event_timer_add(0.10)
        except Exception:
            self._timer = wm.event_timer_add(0.10)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            return self._finish(context, "Abgebrochen", cancel=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scn = context.scene

        # PHASE 1: FIND (Find Low & Jump)
        if self.phase == "FIND":
            try:
                bpy.ops.clip.find_low_and_jump()
            except Exception as exc:
                return self._finish(context, f"FindLow konnte nicht gestartet werden: {exc}", cancel=True)
            data = scn.get("tco_last_findlowjump") or {}
            status = str((data or {}).get("status", "")).upper()
            if status == "OK":
                # Frame gefunden → weiter zu DETECT
                self.phase = "DETECT"
                self.detect_started = False
                self.track_started = False
                return {'RUNNING_MODAL'}
            if status in {"NONE", ""}:
                # Nichts mehr zu finden → Clean-Cycle ausführen und dann Solve starten
                try:
                    bpy.ops.clip.clean_cycle()
                    self.report({'INFO'}, "Clean-Cycle ausgeführt")
                except Exception as exc:
                    self.report({'WARNING'}, f"Clean-Cycle konnte nicht gestartet werden: {exc}")
                # Solve (modal) starten und in SOLVE_WAIT wechseln
                try:
                    bpy.ops.clip.solve_camera_modal('INVOKE_DEFAULT')
                    self.phase = "SOLVE_WAIT"
                    return {'RUNNING_MODAL'}
                except Exception as exc:
                    return self._finish(context, f"Solve konnte nicht gestartet werden: {exc}", cancel=True)
            # Fehlerfall
            return self._finish(context, f"FindLow fehlgeschlagen: {data}", cancel=True)

        # PHASE: SOLVE_WAIT – warte auf Flags aus solve_clean_O
        if self.phase == "SOLVE_WAIT":
            active = bool(scn.get("tco_solve_active", False))
            done = bool(scn.get("tco_solve_done", False))
            if active and not done:
                return {'RUNNING_MODAL'}
            if done:
                reduce_executed = bool(scn.get("tco_reduce_executed", False))
                ae = scn.get("tco_solve_avg_error", None)
                try:
                    thr_scene = float(scn.get("error_track", 2.0))
                except Exception:
                    thr_scene = 2.0
                # Flags optional bereinigen (lassen avg_error stehen zur Info)
                for k in ("tco_solve_active", "tco_solve_done", "tco_reduce_executed"):
                    try:
                        del scn[k]
                    except Exception:
                        pass
                if reduce_executed:
                    # zurück zu FIND
                    self.phase = "FIND"
                    self.detect_started = False
                    self.track_started = False
                    self.report({'INFO'}, "Solve: Reduce ausgeführt → zurück zu FIND")
                    return {'RUNNING_MODAL'}
                # Kein Reduce: ggf. solve_test ausführen, wenn  error_track < ae <= 10
                try:
                    ae_val = float(ae) if ae is not None else None
                except Exception:
                    ae_val = None
                if (ae_val is not None) and (ae_val > thr_scene) and (ae_val <= 10.0):
                    try:
                        bpy.ops.clip.solve_test('INVOKE_DEFAULT')
                        self.phase = "SOLVE_TEST_WAIT"
                        return {'RUNNING_MODAL'}
                    except Exception as exc:
                        self.report({'WARNING'}, f"Solve-Test konnte nicht gestartet werden: {exc}")
                        return self._finish(context, "Solve abgeschlossen – Coordinator beendet.")
                # Abschluss nach Solve
                return self._finish(context, "Solve abgeschlossen – Coordinator beendet.")
            return {'RUNNING_MODAL'}

        # PHASE: SOLVE_TEST_WAIT – warte auf Ende des Solve-Tests, starte dann Refine-Solve
        if self.phase == "SOLVE_TEST_WAIT":
            if bool(scn.get("tco_solve_test_active", False)):
                return {'RUNNING_MODAL'}
            # Test ist fertig → Refine-Solve starten
            try:
                bpy.ops.clip.refine_solve_modal('INVOKE_DEFAULT')
                self.phase = "REFINE_WAIT"
                return {'RUNNING_MODAL'}
            except Exception as exc:
                self.report({'WARNING'}, f"Refine-Solve konnte nicht gestartet werden: {exc}")
                return self._finish(context, "Solve-Test abgeschlossen – Coordinator beendet.")

        # PHASE: REFINE_WAIT – warte auf Flags aus refine_solve_O
        if self.phase == "REFINE_WAIT":
            if bool(scn.get("tco_refine_active", False)) and not bool(scn.get("tco_refine_done", False)):
                return {'RUNNING_MODAL'}
            if bool(scn.get("tco_refine_done", False)):
                reduce_executed = bool(scn.get("tco_reduce_executed", False))
                # Flags bereinigen
                for k in ("tco_refine_active", "tco_refine_done", "tco_reduce_executed"):
                    try:
                        del scn[k]
                    except Exception:
                        pass
                if reduce_executed:
                    self.phase = "FIND"
                    self.detect_started = False
                    self.track_started = False
                    self.report({'INFO'}, "Refine-Solve: Reduce ausgeführt → zurück zu FIND")
                    return {'RUNNING_MODAL'}
                return self._finish(context, "Refine-Solve abgeschlossen – Coordinator beendet.")
            return {'RUNNING_MODAL'}

        # PHASE 2: DETECT
        if self.phase == "DETECT":
            if not self.detect_started:
                try:
                    scn["tco_detect_active"] = False
                except Exception:
                    pass
                try:
                    bpy.ops.clip.detect_cycle('INVOKE_DEFAULT')
                    self.detect_started = True
                    self.report({'INFO'}, "Detect gestartet")
                except Exception as exc:
                    return self._finish(context, f"Detect konnte nicht gestartet werden: {exc}", cancel=True)
                return {'RUNNING_MODAL'}
            # Warten bis Detect beendet ist
            if bool(scn.get("tco_detect_active", False)):
                return {'RUNNING_MODAL'}
            # Detect beendet → Ergebnis prüfen
            res = scn.get("tco_last_detect_cycle") or {}
            count_info = res.get("count") or {}
            status = str(count_info.get("status", "")).upper()
            if status == "ENOUGH":
                # weiter zu TRACK
                self.phase = "TRACK"
                self.track_started = False
                return {'RUNNING_MODAL'}
            # Nicht genug → zurück zu FIND und erneut versuchen
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        # PHASE 3: TRACK (Bidirectional-Track)
        if self.phase == "TRACK":
            if CLIP_OT_bidirectional_track is None:
                # Helper nicht verfügbar → direkt zurück zu FIND
                self.report({'WARNING'}, "Bidirectional-Track nicht verfügbar – übersprungen")
                self.phase = "FIND"
                return {'RUNNING_MODAL'}
            if not self.track_started:
                # sicherstellen, dass der Operator registriert ist
                try:
                    bpy.utils.register_class(CLIP_OT_bidirectional_track)
                except Exception:
                    pass
                try:
                    bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                    self.track_started = True
                    self.report({'INFO'}, "Track gestartet")
                except Exception as exc:
                    self.report({'WARNING'}, f"Track konnte nicht gestartet werden: {exc}")
                    self.phase = "FIND"
                return {'RUNNING_MODAL'}
            # warten bis Track beendet ist
            if bool(scn.get("bidi_active", False)):
                return {'RUNNING_MODAL'}
            # abgeschlossen → Ergebnis optional melden und zurück zu FIND
            result = str(scn.get("bidi_result", ""))
            if result and result != "OK":
                self.report({'WARNING'}, f"Track Ergebnis: {result}")
            else:
                self.report({'INFO'}, "Track abgeschlossen")
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        # Fallback
        return self._finish(context, f"Unbekannte Phase: {self.phase}", cancel=True)


def register():
    # Optional Helper-Operator zuerst registrieren
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.register_class(CLIP_OT_bidirectional_track)
        except Exception:
            pass
    bpy.utils.register_class(CLIP_OT_camera_tracking_coordinator)


def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_camera_tracking_coordinator)
    except Exception:
        pass
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
        except Exception:
            pass