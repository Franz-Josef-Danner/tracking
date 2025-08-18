# Helper/optimize_tracking_modal.py
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
            self._step = 1
            return {"RUNNING_MODAL"}

        if self._step == 1:
            self._log("Step 1: Optimize-Pass")
            # Beispiel: vorhandenen Helper-Operator aufrufen (falls registriert)
            try:
                bpy.ops.clip.marker_helper_main("EXEC_DEFAULT")
                self._log("marker_helper_main EXEC_DEFAULT ok")
            except Exception as ex:
                self._log(f"marker_helper_main skipped/failed: {ex}")
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
    ctx = context or bpy.context
    scn = ctx.scene
    print(f"[Optimize] Fallback run on frame {scn.frame_current}")
    try:
        bpy.ops.clip.marker_helper_main("EXEC_DEFAULT")
        print("[Optimize] marker_helper_main EXEC_DEFAULT ok")
    except Exception as ex:
        print(f"[Optimize] marker_helper_main skipped/failed: {ex}")

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
