# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Bootstrap → Detect → BiDi (mit CLIP-Context-Override)
"""

from __future__ import annotations
import bpy

# Detect aus Helper-Paket (Coordinator liegt in Operator/)
from ..Helper import detect  # Pfad beibehalten

# Scene-Keys
_LOCK_KEY = "tco_lock"
_BIDI_ACTIVE_KEY = "tco_bidi_active"
_BIDI_RESULT_KEY = "tco_bidi_result"
_GOTO_KEY = "tco_goto"
_DEFAULT_SPIKE_START = 50.0

_DETECT_DONE_KEY = "tco_detect_done"
_LAST_DETECT_RESULT_KEY = "tco_last_detect_result"

__all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")


# ---------------------------------------------------------------------------
# UI/Context-Utilities (analog zu detect._run_in_clip_context)
# ---------------------------------------------------------------------------
def _find_clip_context():
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return window, area, region, space
    return None, None, None, None


def _run_in_clip_context(op_callable, **kwargs):
    window, area, region, space = _find_clip_context()
    if not (window and area and region and space):
        # Fallback: ohne Override ausführen
        return op_callable(**kwargs)
    override = {
        "window": window,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    with bpy.context.temp_override(**override):
        return op_callable(**kwargs)


def _start_bidi_operator(context: bpy.types.Context) -> bool:
    # Operator vorhanden?
    if not hasattr(bpy.ops.clip, "bidirectional_track"):
        context.scene[_BIDI_RESULT_KEY] = "OP_NOT_FOUND"
        return False

    # Im CLIP-Kontext starten
    def _op(**kw):
        return bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')

    try:
        ret = _run_in_clip_context(_op)
        ok = (ret in ({'RUNNING_MODAL'}, {'FINISHED'}) or ret == {'RUNNING_MODAL'} or ret == {'FINISHED'})
        if ok:
            context.scene[_BIDI_ACTIVE_KEY] = True
            context.scene[_BIDI_RESULT_KEY] = "STARTED"
        else:
            context.scene[_BIDI_RESULT_KEY] = f"RET:{ret}"
        return bool(ok)
    except Exception as exc:
        context.scene[_BIDI_RESULT_KEY] = f"EXC:{exc}"
        return False


# ---------------------------------------------------------------------------
# Bootstrap + Orchestration
# ---------------------------------------------------------------------------
def bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene

    # Reset
    scn[_LOCK_KEY] = False
    scn[_BIDI_ACTIVE_KEY] = False
    scn[_BIDI_RESULT_KEY] = ""
    scn.pop(_GOTO_KEY, None)
    scn[_DETECT_DONE_KEY] = False
    scn[_LAST_DETECT_RESULT_KEY] = {}

    # State-Container
    scn["tco_state"] = {
        "state": "INIT",
        "detect_attempts": 0,
        "bidi_started": False,
        "repeat_map": {},
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

    # Detect adaptiv ausführen
    try:
        det = detect.run_detect_adaptive(context, max_attempts=5)
    except Exception as exc:
        det = {"status": "FAILED", "reason": f"detect_exception: {exc}"}

    scn[_LAST_DETECT_RESULT_KEY] = det
    st = det.get("status", "FAILED")
    if st == "READY":
        scn[_DETECT_DONE_KEY] = True
        scn["tco_state"]["state"] = "DETECT_READY"
    else:
        scn[_DETECT_DONE_KEY] = False
        scn["tco_state"]["state"] = f"DETECT_{st}"

    # BiDi nur bei erfolgreichem Detect
    if scn[_DETECT_DONE_KEY]:
        started = _start_bidi_operator(context)
        scn["tco_state"]["bidi_started"] = bool(started)
    else:
        scn["tco_state"]["bidi_started"] = False


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------
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
