import bpy
from bpy.types import Operator

# Optionaler Direktimport für Fallback
try:
    from .bootstrap_O import CLIP_OT_bootstrap_cycle  # type: ignore
except Exception:
    CLIP_OT_bootstrap_cycle = None  # type: ignore

__all__ = ("CLIP_OT_camera_tracking_coordinator",)


class CLIP_OT_camera_tracking_coordinator(Operator):
    """Modaler 3er‑Ablauf: FIND → DETECT → TRACK; Wiederholen bis FIND nichts mehr findet."""

    bl_idname = "clip.camera_tracking_coordinator"
    bl_label = "Camera Tracking Coordinator"
    bl_options = {"REGISTER", "UNDO"}

    # Runtime‑State
    _timer: object | None = None
    phase: str = "FIND"
    detect_started: bool = False

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
                return {'RUNNING_MODAL'}
            if status in {"NONE", ""}:
                # Nichts mehr zu finden → fertig
                return self._finish(context, "Kein Low‑Marker‑Frame mehr gefunden – fertig.")
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
                self.phase = "TRACK"
                return {'RUNNING_MODAL'}
            # Nicht genug → zurück zu FIND und erneut versuchen
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        # PHASE 3: TRACK (Solve einmal ausführen)
        if self.phase == "TRACK":
            try:
                bpy.ops.clip.solve_cycle()
            except Exception as exc:
                self.report({'WARNING'}, f"Solve fehlgeschlagen: {exc}")
            # Danach wieder von vorne
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        # Fallback
        return self._finish(context, f"Unbekannte Phase: {self.phase}", cancel=True)


def register():
    bpy.utils.register_class(CLIP_OT_camera_tracking_coordinator)


def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_camera_tracking_coordinator)
    except Exception:
        pass