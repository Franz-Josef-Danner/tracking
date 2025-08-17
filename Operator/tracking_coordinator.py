# Operator/tracking_lowjump.py
# Minimal-Operator: Find Low-Marker-Frame → JumpToFrame

import bpy
from typing import Set

LOCK_KEY = "__detect_lock"


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Finde Low-Marker-Frame und springe dorthin"""

    bl_idname = "clip.lowjump"
    bl_label = "Find & Jump to Low-Marker Frame"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _state: str = "INIT"
    _settle_ticks: int = 0
    _jump_done: bool = False

    def _log(self, msg: str) -> None:
        print(f"[LowJump] {msg}")

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
        self._state = "DONE"
        return {"CANCELLED"}

    # ------------------------------------------------------------
    # Blender Hooks
    # ------------------------------------------------------------
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        self._state = "FIND_LOW"
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._log("Start")
        return {"RUNNING_MODAL"}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        return self.invoke(context, None)

    # ------------------------------------------------------------
    # Modal FSM
    # ------------------------------------------------------------
    def modal(self, context: bpy.types.Context, event) -> Set[str]:
        if event.type == "ESC":
            return self._cancel(context, "ESC gedrückt")

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if not context.area or context.area.type != "CLIP_EDITOR":
            return self._cancel(context, "CLIP_EDITOR verloren")

        # --- FSM ---
        if self._state == "FIND_LOW":
            try:
                from ..Helper.find_low_marker_frame import run_find_low_marker_frame
                res = run_find_low_marker_frame(context) or {}
            except Exception as ex:
                self._log(f"[FindLow] Fehler: {ex}")
                res = {"status": "FAILED"}

            if res.get("status") == "FOUND":
                goto = int(res.get("frame", context.scene.frame_current))
                context.scene["goto_frame"] = goto
                self._log(f"[FindLow] Frame {goto} gefunden")
                self._jump_done = False
                self._state = "JUMP"
            elif res.get("status") == "NONE":
                self._log("[FindLow] Kein Low-Marker-Frame gefunden → fertig")
                self._state = "DONE"
                return {"FINISHED"}
            else:
                self._log("[FindLow] Fehler/kein Ergebnis – abbrechen")
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

            self._log("[LowJump] Fertig – Operator endet")
            self._state = "DONE"
            return {"FINISHED"}

        elif self._state == "DONE":
            self._remove_timer(context)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}


# Registration
def register():
    bpy.utils.register_class(CLIP_OT_lowjump)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_lowjump)
