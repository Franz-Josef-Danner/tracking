# Operator/tracking_coordinator.py
# Reduzierter Orchestrator: FIND_LOW → JUMP → WAIT → FINISHED
# Beibehaltung von Klassenname & bl_idname für Kompatibilität.

from __future__ import annotations

import bpy
from typing import Set

LOCK_KEY = "__detect_lock"

__all__ = ("CLIP_OT_tracking_coordinator",)


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Findet den nächsten Low-Marker-Frame und springt dorthin (Reduced Mode)."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Pipeline)"
    bl_options = {"REGISTER", "UNDO"}

    # Nur noch für Timer-Steuerung relevant
    poll_every: bpy.props.FloatProperty(
        name="Poll Every (s)",
        default=0.05,
        min=0.01,
        description="Modal poll period",
    )

    # ---- Runtime ----
    _timer = None
    _state: str = "INIT"
    _jump_done: bool = False
    _settle_ticks: int = 0

    # --------------------------
    # intern
    # --------------------------
    def _log(self, msg: str) -> None:
        print(f"[Coordinator] {msg}")

    def _remove_timer(self, context: bpy.types.Context) -> None:
        try:
            wm = context.window_manager
            if self._timer:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None

    def _cancel(self, context: bpy.types.Context, reason: str = "Cancelled") -> Set[str]:
        self._log(f"Abbruch: {reason}")
        self._remove_timer(context)
        try:
            context.scene[LOCK_KEY] = False
        except Exception:
            pass
        self._state = "DONE"
        return {"CANCELLED"}

    def _bootstrap(self, context: bpy.types.Context) -> None:
        self._state = "FIND_LOW"
        self._jump_done = False
        self._settle_ticks = 0
        try:
            # Lock aufräumen, falls irgendwo noch gesetzt
            context.scene[LOCK_KEY] = False
        except Exception:
            pass

    # --------------------------
    # Blender Hooks
    # --------------------------
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        self._bootstrap(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_every, window=context.window)
        wm.modal_handler_add(self)
        self._log("Start (Reduced Mode: FIND_LOW → JUMP)")
        return {"RUNNING_MODAL"}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        return self.invoke(context, None)

    # --------------------------
    # Modal FSM (reduziert)
    # --------------------------
    def modal(self, context: bpy.types.Context, event) -> Set[str]:
        # Globaler Detect/Cleanup-Lock respektieren, auch wenn wir ihn nicht setzen.
        try:
            if context.scene.get(LOCK_KEY, False):
                return {"RUNNING_MODAL"}
        except Exception:
            pass

        if event.type == "ESC":
            return self._cancel(context, "ESC gedrückt")

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if not context.area or context.area.type != "CLIP_EDITOR":
            return self._cancel(context, "CLIP_EDITOR-Kontext verloren")

        # --- FSM ---
        if self._state == "FIND_LOW":
            try:
                from ..Helper.find_low_marker_frame import run_find_low_marker_frame
                res = run_find_low_marker_frame(context) or {}
            except Exception as ex:
                self._log(f"[FindLow] Fehler: {ex}")
                res = {"status": "FAILED"}

            st = res.get("status", "FAILED")
            if st == "FOUND":
                goto = int(res.get("frame", context.scene.frame_current))
                context.scene["goto_frame"] = goto
                self._log(f"[FindLow] Low-Marker-Frame gefunden: {goto}")
                self._jump_done = False
                self._state = "JUMP"
            elif st == "NONE":
                self._log("[FindLow] Kein Low-Marker-Frame gefunden – fertig")
                self._state = "DONE"
                return {"FINISHED"}
            else:
                return self._cancel(context, "FindLow fehlgeschlagen")
            return {"RUNNING_MODAL"}

        elif self._state == "JUMP":
            goto = int(context.scene.get("goto_frame", context.scene.frame_current))
            cur = context.scene.frame_current
            if not self._jump_done or goto != cur:
                try:
                    from ..Helper.jump_to_frame import run_jump_to_frame
                    run_jump_to_frame(context, frame=goto)
                    self._log(f"[Jump] Playhead auf Frame {goto} gesetzt")
                except Exception as ex:
                    self._log(f"[Jump] Fehler: {ex}")
                self._jump_done = True
            # kurze Beruhigung, damit UI/Depsgraph stabil ist
            self._settle_ticks = 2
            self._state = "WAIT_GOTO"
            return {"RUNNING_MODAL"}

        elif self._state == "WAIT_GOTO":
            if self._settle_ticks > 0:
                self._settle_ticks -= 1
                try:
                    context.view_layer.update()
                except Exception:
                    pass
                try:
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                except Exception:
                    pass
                return {"RUNNING_MODAL"}

            self._log("[Reduced] Fertig (Jump abgeschlossen)")
            self._state = "DONE"
            return {"FINISHED"}

        elif self._state == "DONE":
            self._remove_timer(context)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}


def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
