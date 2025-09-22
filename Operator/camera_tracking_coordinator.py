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

# Optional: Reducer für hohe Fehlerwerte
try:
    from ..Helper.reduce_error_tracks import run_reduce_error_tracks  # type: ignore
except Exception:
    run_reduce_error_tracks = None  # type: ignore

__all__ = ("CLIP_OT_camera_tracking_coordinator",)


class CLIP_OT_camera_tracking_coordinator(Operator):
    """Modaler Ablauf: FIND → DETECT → TRACK; Wiederholen bis FIND nichts mehr findet.
    Wenn FIND nichts mehr findet: Clean-Cycle ausführen und beenden.
    """

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
                # Nichts mehr zu finden → Clean-Cycle ausführen und dann erneut prüfen
                try:
                    bpy.ops.clip.clean_cycle()
                    self.report({'INFO'}, "Clean-Cycle ausgeführt")
                except Exception as exc:
                    self.report({'WARNING'}, f"Clean-Cycle konnte nicht gestartet werden: {exc}")
                # Auswertung des Clean-Resultats
                restart = False
                deleted_total = 0
                fm_status = ""
                try:
                    res_clean = scn.get("tco_last_clean_cycle") or {}
                    restart = bool(res_clean.get("restart", False))
                    deleted_total = int(res_clean.get("markers_deleted_total", 0) or 0)
                    steps = res_clean.get("steps") or []
                    if isinstance(steps, (list, tuple)):
                        for s in steps:
                            try:
                                if str(s.get("step", "")) == "find_max_marker_frame":
                                    fm_status = str(s.get("status", ""))
                                    break
                            except Exception:
                                pass
                except Exception:
                    restart = False
                # Entscheidungslogik:
                # 1) Wenn Restart gewünscht ODER Marker gelöscht wurden → zurück zu FIND
                # 2) Wenn nichts gelöscht wurde UND find_max == NONE → Solve starten; wenn Solve Tracks gelöscht hat → zurück zu FIND, sonst ggf. Reducer, sonst beenden
                if not restart and int(deleted_total) == 0 and str(fm_status).upper() in {"NONE", ""}:
                    try:
                        bpy.ops.clip.solve_cycle()
                        # Prüfen, ob nach dem Solve unreconstructed Tracks entfernt wurden
                        cleanup = scn.get("tco_last_unreconstructed_cleanup") or {}
                        try:
                            deleted_after_solve = int((cleanup.get("deleted", 0) or 0))
                        except Exception:
                            deleted_after_solve = 0
                        if deleted_after_solve > 0:
                            # zurück zu FIND
                            self.phase = "FIND"
                            self.detect_started = False
                            self.track_started = False
                            self.report({'INFO'}, f"Solve: {deleted_after_solve} Tracks gelöscht → zurück zu FIND")
                            return {'RUNNING_MODAL'}
                        # Keine Löschungen → ggf. Reduce-Phase, falls avg_error > error_track
                        try:
                            res_solve = scn.get("tco_last_solve_cycle") or {}
                            ae = res_solve.get("avg_error", None)
                            try:
                                avg_err = float(ae)
                            except Exception:
                                avg_err = None
                            thr_scene = float(scn.get("error_track", 2.0))
                        except Exception:
                            avg_err = None
                            thr_scene = 2.0
                        if (avg_err is not None) and (avg_err > thr_scene) and (run_reduce_error_tracks is not None):
                            # Threshold temporär auf 10.0 setzen
                            old_thr = scn.get("error_track", None)
                            try:
                                scn["error_track"] = 10.0
                            except Exception:
                                pass
                            try:
                                res_red = run_reduce_error_tracks(context)
                                # optional Telemetrie ablegen
                                try:
                                    scn["tco_last_reduce_error_tracks"] = res_red
                                except Exception:
                                    pass
                                self.report({'INFO'}, f"Reduce-Error-Tracks ausgeführt (thr=10): deleted={int(res_red.get('deleted',0))}")
                            except Exception as _rex:
                                self.report({'WARNING'}, f"Reduce-Error-Tracks Fehler: {_rex}")
                            finally:
                                # ursprünglichen Threshold wiederherstellen
                                try:
                                    if old_thr is None:
                                        del scn["error_track"]
                                    else:
                                        scn["error_track"] = old_thr
                                except Exception:
                                    pass
                            # zurück zu FIND
                            self.phase = "FIND"
                            self.detect_started = False
                            self.track_started = False
                            return {'RUNNING_MODAL'}
                        # keine Löschungen und kein Reducer nötig → Coordinator beenden
                        return self._finish(context, "Solve-Cycle abgeschlossen – Coordinator beendet.")
                    except Exception as exc:
                        return self._finish(context, f"Solve-Cycle konnte nicht gestartet/ausgeführt werden: {exc}", cancel=True)
                # ansonsten zurück zu FIND
                self.phase = "FIND"
                self.detect_started = False
                self.track_started = False
                return {'RUNNING_MODAL'}
            # Fehlerfall
            return self._finish(context, f"FindLow fehlgeschlagen: {data}", cancel=True)

        # PHASE 2: DETECT (modaler Operator, wir warten auf Scene‑Flag)
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