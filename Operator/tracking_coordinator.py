# tracking_coordinator.py
# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Bootstrap → Detect → Bidirectional Track
"""

from __future__ import annotations
import bpy

# Detect aus dem Helper-Paket
from ..Helper import detect  # ggf. Pfad anpassen

# Scene-Keys
_LOCK_KEY = "tco_lock"
_BIDI_ACTIVE_KEY = "tco_bidi_active"
_BIDI_RESULT_KEY = "tco_bidi_result"
_GOTO_KEY = "tco_goto"
_DEFAULT_SPIKE_START = 50.0

# zusätzliche, klare Flags
_DETECT_DONE_KEY = "tco_detect_done"
_LAST_DETECT_RESULT_KEY = "tco_last_detect_result"

__all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")


def _run_bidi_operator(context: bpy.types.Context) -> bool:
    """Startet den bidirektionalen Tracking-Operator im gültigen UI-Kontext."""
    try:
        # Operator feuern (arbeitet modal mit Timer)
        ret = bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
        ok = (ret in ({'RUNNING_MODAL'}, {'FINISHED'}) or ret == {'RUNNING_MODAL'} or ret == {'FINISHED'})
        if ok:
            context.scene[_BIDI_ACTIVE_KEY] = True
        return bool(ok)
    except Exception:
        return False


def bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene

    # --- Reset der globalen Flags ---
    scn[_LOCK_KEY] = False
    scn[_BIDI_ACTIVE_KEY] = False
    scn[_BIDI_RESULT_KEY] = ""
    scn.pop(_GOTO_KEY, None)
    scn[_DETECT_DONE_KEY] = False
    scn[_LAST_DETECT_RESULT_KEY] = {}

    # --- Orchestrator-Statuscontainer ---
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

    # --- DETECT direkt ausführen (adaptiv bis READY/FAILED) ---
    try:
        result = detect.run_detect_adaptive(context, max_attempts=5)
    except Exception as exc:
        result = {"status": "FAILED", "reason": f"detect_exception: {exc}"}

    scn[_LAST_DETECT_RESULT_KEY] = result

    # Robust: zusätzlich ein simples Flag setzen, falls READY
    if result.get("status") == "READY":
        scn[_DETECT_DONE_KEY] = True
        scn["tco_state"]["state"] = "DETECT_READY"
    else:
        scn[_DETECT_DONE_KEY] = False
        scn["tco_state"]["state"] = f"DETECT_{result.get('status', 'FAILED')}"

    # --- Wenn Detect fertig/ok → BiDi starten ---
    if scn[_DETECT_DONE_KEY] is True:
        started = _run_bidi_operator(context)
        scn["tco_state"]["bidi_started"] = bool(started)
        if not started:
            scn[_BIDI_RESULT_KEY] = "FAILED_TO_START"
    else:
        # Kein BiDi-Start bei nicht erfolgreichem Detect
        scn["tco_state"]["bidi_started"] = False


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Coordinator (Bootstrap → Detect → BiDi)"""
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
        # Kurzes, klares Reporting
        st = context.scene.get("tco_state", {}).get("state", "UNKNOWN")
        bidi = context.scene.get("tco_state", {}).get("bidi_started", False)
        self.report({'INFO'}, f"Coordinator complete → {st}; BiDi started={bidi}")
        return {'FINISHED'}


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
