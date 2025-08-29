# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Orchestrator-Zyklus (find → jump → detect → bidi)
- Start via Operator-Button (CLIP_EDITOR).
- Modal gesteuerte, konfliktfreie Sequenz mit Scene-Flags.
"""

from __future__ import annotations
import bpy
from typing import Dict

# -------------------------
# robuste Importe (Package/Flat)
# -------------------------
try:
    from ..Helper.find_low_marker_frame import run_find_low_marker_frame
except Exception:
    from Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore

try:
    from ..Helper.jump_to_frame import run_jump_to_frame
except Exception:
    from Helper.jump_to_frame import run_jump_to_frame  # type: ignore

try:
    from ..Helper.detect import run_detect_adaptive
except Exception:
    from Helper.detect import run_detect_adaptive  # type: ignore

# Scene Keys
K_CYCLE_ACTIVE   = "tco_cycle_active"
K_PHASE          = "tco_phase"
K_LAST           = "tco_last"
K_GOTO_FRAME     = "goto_frame"
K_BIDI_ACTIVE    = "bidi_active"
K_BIDI_RESULT    = "bidi_result"
K_DETECT_LOCK    = "__detect_lock"

PH_FIND   = "FIND_LOW"
PH_JUMP   = "JUMP"
PH_DETECT = "DETECT"
PH_BIDI_S = "BIDI_START"
PH_BIDI_W = "BIDI_WAIT"
PH_FIN    = "FINISH"

TIMER_SEC = 0.20

__all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")  # <-- WICHTIG

# -------------------------
# Bootstrap (intern)
# -------------------------
def _bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene
    scn[K_CYCLE_ACTIVE] = True
    scn[K_PHASE] = PH_FIND
    scn[K_LAST] = {}
    scn.pop(K_GOTO_FRAME, None)
    scn.pop(K_BIDI_RESULT, None)
    scn[K_BIDI_ACTIVE] = False

# Öffentlicher Wrapper für Alt-Code, der `from ... import bootstrap` nutzt
def bootstrap(context: bpy.types.Context) -> None:
    _bootstrap(context)

# -------------------------
# Operator
# -------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking-Zyklus koordinieren (find→jump→detect→bidi)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator starten"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _repeat_map: Dict[int, int] = {}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context is not None and context.scene is not None

    def execute(self, context: bpy.types.Context):
        _bootstrap(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(TIMER_SEC, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Coordinator gestartet.")
        return {'RUNNING_MODAL'}

    def cancel(self, context: bpy.types.Context):
        self._cleanup(context)

    def _cleanup(self, context: bpy.types.Context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        try:
            context.scene[K_CYCLE_ACTIVE] = False
        except Exception:
            pass

    def modal(self, context: bpy.types.Context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        scn = context.scene
        if not scn.get(K_CYCLE_ACTIVE, False):
            return self._finish(context)

        phase = scn.get(K_PHASE, PH_FIND)

        # ---- FIND_LOW ----
        if phase == PH_FIND:
            res = run_find_low_marker_frame(context)
            scn[K_LAST] = {"phase": PH_FIND, **res}
            st = res.get("status")
            if st == "FOUND":
                scn[K_GOTO_FRAME] = int(res["frame"])
                scn[K_PHASE] = PH_JUMP
            elif st == "NONE":
                scn[K_PHASE] = PH_FIN
            else:
                scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        # ---- JUMP ----
        if phase == PH_JUMP:
            res = run_jump_to_frame(context, frame=scn.get(K_GOTO_FRAME), repeat_map=self._repeat_map)
            scn[K_LAST] = {"phase": PH_JUMP, **res}
            scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        # ---- DETECT ----
        if phase == PH_DETECT:
            if scn.get(K_DETECT_LOCK, False):
                return {'RUNNING_MODAL'}  # warten, wenn detect intern locked
            res = run_detect_adaptive(
                context,
                start_frame=None,
                max_attempts=4,
                selection_policy="only_new",
                duplicate_strategy="delete",
                post_pattern_triplet=True,
            )
            scn[K_LAST] = {"phase": PH_DETECT, **res}
            scn[K_PHASE] = PH_BIDI_S
            return {'RUNNING_MODAL'}

        # ---- BIDI_START ----
        if phase == PH_BIDI_S:
            if scn.get(K_BIDI_ACTIVE, False):
                scn[K_PHASE] = PH_BIDI_W
                return {'RUNNING_MODAL'}
            try:
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                scn[K_PHASE] = PH_BIDI_W
            except Exception as ex:
                scn[K_LAST] = {"phase": PH_BIDI_S, "status": "FAILED", "reason": str(ex)}
                scn[K_PHASE] = PH_FIND
            return {'RUNNING_MODAL'}

        # ---- BIDI_WAIT ----
        if phase == PH_BIDI_W:
            if scn.get(K_BIDI_ACTIVE, False):
                return {'RUNNING_MODAL'}
            scn[K_LAST] = {"phase": PH_BIDI_W, "bidi_result": scn.get(K_BIDI_RESULT, "")}
            scn[K_PHASE] = PH_FIND
            return {'RUNNING_MODAL'}

        # ---- FINISH ----
        if phase == PH_FIN:
            return self._finish(context)

        scn[K_PHASE] = PH_FIND
        return {'RUNNING_MODAL'}

    def _finish(self, context: bpy.types.Context):
        self._cleanup(context)
        self.report({'INFO'}, "Coordinator beendet.")
        return {'FINISHED'}

# -------------------------
# Registrierung
# -------------------------
def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)

if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
