# tracking_coordinator.py
# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Minimaler Coordinator mit Bootstrap + Detect
"""

from __future__ import annotations
import bpy

# Import der Detect-Routine
from ..Helper import detect  # Pfad ggf. anpassen

_LOCK_KEY = "tco_lock"
_BIDI_ACTIVE_KEY = "tco_bidi_active"
_BIDI_RESULT_KEY = "tco_bidi_result"
_GOTO_KEY = "tco_goto"
_DEFAULT_SPIKE_START = 50.0

__all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")


def bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene

    # Globale Scene-Flags
    scn[_LOCK_KEY] = False
    scn[_BIDI_ACTIVE_KEY] = False
    scn[_BIDI_RESULT_KEY] = ""
    scn.pop(_GOTO_KEY, None)

    scn["tco_state"] = {
        "state": "INIT",
        "detect_attempts": 0,
        "jump_done": False,
        "repeat_map": {},
        "bidi_started": False,
        "cycle_active": False,
        "cycle_target_frame": None,
        "cycle_iterations": 0,
        "spike_threshold": float(
            getattr(scn, "spike_start_threshold", _DEFAULT_SPIKE_START) or _DEFAULT_SPIKE_START
        ),
        "spike_floor": 10.0,
        "spike_floor_hit": False,
        "pending_eval_after_solve": False,
        "did_refine_this_cycle": False,
        "last_solve_error": None,
        "same_error_repeat_count": 0,
    }

    # --- NEU: Detect direkt starten ---
    try:
        result = detect.run_detect_adaptive(context, max_attempts=5)
        scn["tco_state"]["last_detect_result"] = result
    except Exception as exc:
        scn["tco_state"]["last_detect_result"] = {"status": "FAILED", "reason": str(exc)}


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking Coordinator Bootstrap + Detect"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator starten"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context is not None and context.scene is not None

    def execute(self, context: bpy.types.Context):
        try:
            bootstrap(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Bootstrap failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator bootstrap + detect complete.")
        return {'FINISHED'}
