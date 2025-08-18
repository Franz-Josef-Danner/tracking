# Helper/optimize_tracking_modal.py
# Modal-Helper ohne marker_helper_main: nutzt nur Scene-Werte, klare Logs, sauberer Modal-Lifecycle.

from __future__ import annotations
import bpy
from typing import Set

__all__ = ["CLIP_OT_optimize_tracking_modal", "run_optimize_tracking_modal"]


class CLIP_OT_optimize_tracking_modal(bpy.types.Operator):
    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimize Tracking (Modal)"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _step = 0

    @classmethod
    def poll(cls, context):
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def _log(self, msg: str) -> None:
        print(f"[Optimize] {msg}")

    def _read_scene_values(self, scene):
        """Liest die im Pre-Hook gesetzten Werte (falls vorhanden) und loggt sie."""
        ma = scene.get("marker_adapt")
        mn = scene.get("marker_min")
        mx = scene.get("marker_max")
        self._log(f"Scene Values → adapt={ma}, min={mn}, max={mx}")
        return ma, mn, mx

    def invoke(self, context, event) -> Set[str]:
        wm = context.window_manager
        self._step = 0
        self._timer = wm.event_timer_add(0.15, window=context.window)
        wm.modal_handler_add(self)
        self._log(f"Start (frame={context.scene.frame_current})")
        return {"RUNNING_MODAL"}

    def modal(self, context, event) -> Set[str]:
        if event.type == "ESC":
            return self._cancel(context, "ESC")

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._step == 0:
            self._log("Step 0: Preflight")
            # Nur lesend: was hat der Pre-Hook gesetzt?
            self._read_scene_values(context.scene)
            self._step = 1
            return {"RUNNING_MODAL"}

        if self._step == 1:
            self._log("Step 1: Optimize-Pass (ohne marker_helper_main)")
            # Placeholders für deine künftigen Optimizer-Schritte.
            # Hier kannst du direkt eigene Heuristiken/Parameter-Sweeps einhängen,
            # ohne weitere Operator-Registrierungen.
            # Beispiel: nur als sichtbarer Proof-of-Work ein no-op:
            try:
                context.view_layer.update()
            except Exception:
                pass
            self._step = 2
            return {"RUNNING_MODAL"}

        if self._step == 2:
            self._log("Step 2: Abschluss")
            return self._finish(context)

        return {"RUNNING_MODAL"}

    def _finish(self, context) -> Set[str]:
        self._teardown(context)
        self._log("Done.")
        return {"FINISHED"}

    def _cancel(self, context, reason: str) -> Set[str]:
        self._log(f"Abbruch: {reason}")
        self._teardown(context)
        return {"CANCELLED"}

    def _teardown(self, context) -> None:
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None


def run_optimize_tracking_modal(context: bpy.types.Context | None = None) -> None:
    """Fallback-Funktion: startet den Operator modal, ohne weitere Abhängigkeiten."""
    try:
        bpy.ops.clip.optimize_tracking_modal("INVOKE_DEFAULT")
    except Exception as ex:
        print(f"[Optimize] Fallback-Aufruf fehlgeschlagen: {ex}")


# Lokale Registrierung (optional für Einzeltests)
def register():
    try:
        bpy.utils.register_class(CLIP_OT_optimize_tracking_modal)
    except Exception:
        pass

def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_optimize_tracking_modal)
    except Exception:
        pass
