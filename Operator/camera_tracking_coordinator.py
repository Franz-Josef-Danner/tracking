import bpy
from bpy.types import Operator
import math

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

# Optional: Reset (für Neustarts)
try:
    from ..Helper.reset_state import reset_for_new_cycle  # type: ignore
except Exception:
    reset_for_new_cycle = None  # type: ignore

__all__ = ("CLIP_OT_camera_tracking_coordinator",)


class CLIP_OT_camera_tracking_coordinator(Operator):
    """Modaler Ablauf: FIND → DETECT → TRACK; Wenn nichts zu finden: Solve-Test → ggf. Neustart bei FIND."""

    bl_idname = "clip.camera_tracking_coordinator"
    bl_label = "Camera Tracking Coordinator"
    bl_options = {"REGISTER", "UNDO"}

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
        try:
            print(f"[Coord] phase={self.phase}")
        except Exception:
            pass

        # PHASE: FIND (Find Low & Jump)
        if self.phase == "FIND":
            try:
                bpy.ops.clip.find_low_and_jump()
                print(f"[Coord] find_low invoked; scene.tco_last_findlowjump={scn.get('tco_last_findlowjump')}")
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
                # Statt Clean/Solve → direkt Solve-Test starten
                try:
                    bpy.ops.clip.solve_test('INVOKE_DEFAULT')
                    self.phase = "SOLVE_TEST_WAIT"
                    return {'RUNNING_MODAL'}
                except Exception as exc:
                    self.report({'WARNING'}, f"Solve-Test konnte nicht gestartet werden: {exc}")
                    # Fallback: zurück zu FIND erneut versuchen
                    self.phase = "FIND"
                    return {'RUNNING_MODAL'}
            # Unerwarteter Status → erneut versuchen
            self.report({'WARNING'}, f"FindLow unerwarteter Status: {status} data={data}")
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        # PHASE: SOLVE_TEST_WAIT – warte auf Ende des Test-Solve; ggf. Neustart
        if self.phase == "SOLVE_TEST_WAIT":
            restart = bool(scn.get("tco_restart_find", False))
            active = bool(scn.get("tco_solve_test_active", False))
            print(f"[Coord] SOLVE_TEST_WAIT flags active={active} restart={restart}")
            if restart:
                try:
                    scn["tco_solve_test_active"] = False
                except Exception:
                    pass
                for k in ("tco_restart_find",):
                    try:
                        del scn[k]
                    except Exception:
                        pass
                try:
                    if "tco_last_findlowjump" in scn:
                        del scn["tco_last_findlowjump"]
                except Exception:
                    pass
                if reset_for_new_cycle is not None:
                    try:
                        reset_for_new_cycle(context)
                        print("[Coord] reset_for_new_cycle executed before FindLow")
                    except Exception as exc:
                        print(f"[Coord] reset_for_new_cycle failed: {exc}")
                try:
                    bpy.ops.clip.find_low_and_jump()
                    print(f"[Coord] find_low_and_jump triggered after model switch; result={scn.get('tco_last_findlowjump')}")
                except Exception as exc:
                    print(f"[Coord] find_low_and_jump failed after solve_test: {exc}")
                self.phase = "FIND"
                self.detect_started = False
                self.track_started = False
                self.report({'INFO'}, "Solve-Test: Restart-Flag gesetzt → zurück zu FIND")
                return {'RUNNING_MODAL'}
            if active:
                return {'RUNNING_MODAL'}
            # Kein Restart und Test beendet → Gesamtprozess fertig
            return self._finish(context, "Solve-Test abgeschlossen – Coordinator beendet.")

        # PHASE: DETECT
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
            if bool(scn.get("tco_detect_active", False)):
                return {'RUNNING_MODAL'}
            res = scn.get("tco_last_detect_cycle") or {}
            count_info = res.get("count") or {}
            status = str(count_info.get("status", "")).upper()
            if status == "ENOUGH":
                self.phase = "TRACK"
                self.track_started = False
                return {'RUNNING_MODAL'}
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        # PHASE: TRACK
        if self.phase == "TRACK":
            if CLIP_OT_bidirectional_track is None:
                self.report({'WARNING'}, "Bidirectional-Track nicht verfügbar – übersprungen")
                self.phase = "FIND"
                return {'RUNNING_MODAL'}
            if not self.track_started:
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
            if bool(scn.get("bidi_active", False)):
                return {'RUNNING_MODAL'}
            result = str(scn.get("bidi_result", ""))
            if result and result != "OK":
                self.report({'WARNING'}, f"Track Ergebnis: {result}")
            else:
                self.report({'INFO'}, "Track abgeschlossen")
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        return self._finish(context, f"Unbekannte Phase: {self.phase}", cancel=True)


def register():
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