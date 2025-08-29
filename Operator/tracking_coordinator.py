# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Minimaler Coordinator mit Bootstrap-Reset
- Stellt den Operator `CLIP_OT_tracking_coordinator` bereit (Button-Target).
- Führt beim Ausführen ein definierte(r) Bootstrap/Reset im Scene-State aus.
"""

from __future__ import annotations
import bpy

# --- Keys / Defaults (an Projekt-Konstanten anpassen, falls vorhanden) -----
_LOCK_KEY = "tco_lock"
_BIDI_ACTIVE_KEY = "tco_bidi_active"
_BIDI_RESULT_KEY = "tco_bidi_result"
_GOTO_KEY = "tco_goto"
_DEFAULT_SPIKE_START = 50.0

__all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")


# --- Bootstrap: setzt Scene-Flags und interne Reset-Variablen --------------
def bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene

    # Globale Scene-Flags
    scn[_LOCK_KEY] = False
    scn[_BIDI_ACTIVE_KEY] = False
    scn[_BIDI_RESULT_KEY] = ""
    scn.pop(_GOTO_KEY, None)

    # Interne State-Container (falls später in Scene benötigt, hier persistieren)
    scn["tco_state"] = {
        "state": "INIT",
        "detect_attempts": 0,
        "jump_done": False,
        "repeat_map": {},          # serialisierbar halten
        "bidi_started": False,

        # Cycle
        "cycle_active": False,
        "cycle_target_frame": None,
        "cycle_iterations": 0,

        # Spike
        "spike_threshold": float(
            getattr(scn, "spike_start_threshold", _DEFAULT_SPIKE_START) or _DEFAULT_SPIKE_START
        ),
        "spike_floor": 10.0,
        "spike_floor_hit": False,

        # Solve/Eval/Refine
        "pending_eval_after_solve": False,
        "did_refine_this_cycle": False,

        # Solve-Error-Merker
        "last_solve_error": None,
        "same_error_repeat_count": 0,
    }


# --- Operator: wird vom UI-Button aufgerufen -------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking Coordinator Bootstrap"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator starten"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Optional enger machen: nur im Clip Editor erlauben
        return context is not None and context.scene is not None

    def execute(self, context: bpy.types.Context):
        try:
            bootstrap(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Bootstrap failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator bootstrap reset complete.")
        return {'FINISHED'}


# --- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)


# Optional: lokale Tests beim Direktlauf
if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
