# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Minimaler Coordinator mit Bootstrap-Reset
- Stellt den Operator `CLIP_OT_tracking_coordinator` bereit (Button-Target).
- Führt beim Ausführen ein definierte(r) Bootstrap/Reset im Scene-State aus.
"""

from __future__ import annotations
import bpy
from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame
from ..Helper.detect import run_detect_once
# --- Keys / Defaults (an Projekt-Konstanten anpassen, falls vorhanden) -----
_LOCK_KEY = "tco_lock"
_BIDI_ACTIVE_KEY = "tco_bidi_active"
_BIDI_RESULT_KEY = "tco_bidi_result"
_GOTO_KEY = "tco_goto"
_DEFAULT_SPIKE_START = 50.0
_CYCLE_LOCK_KEY = "tco_cycle_lock"
# Erste, klar definierte Phase des modularen Zyklus
_CYCLE_PHASES = (
    "DETECT",
)
__all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")


# --- Bootstrap: setzt Scene-Flags und interne Reset-Variablen --------------

def _get_state(scn: bpy.types.Scene) -> dict:
    """Kurzhelper für den persistierten State-Container."""
    return scn.get("tco_state", {})


def _cycle_begin(context: bpy.types.Context, *, target_frame: int | None) -> dict:
    """
    Startet einen modularen, synchron abgearbeiteten Zyklus.
    Reentrancy wird über _CYCLE_LOCK_KEY verhindert.
    """
    scn = context.scene
    if scn.get(_CYCLE_LOCK_KEY, False):
        # Bereits aktiv – nicht erneut starten
        return {"status": "SKIPPED", "reason": "cycle_locked"}

    scn[_CYCLE_LOCK_KEY] = True
    try:
        st = _get_state(scn)
        st["cycle_active"] = True
        st["cycle_iterations"] = int(st.get("cycle_iterations", 0)) + 1
        st["cycle_target_frame"] = int(target_frame) if target_frame is not None else int(scn.frame_current)
        st["cycle_phase_index"] = 0
        st["cycle_last_result"] = None
        scn["tco_state"] = st  # zurückschreiben

        # Sofortige, synchrone Abarbeitung der ersten Phase
        return _cycle_step(context)
    finally:
        # Lock unmittelbar wieder lösen; jede Phase läuft synchron im Operator-Kontext,
        # dadurch keine konkurrierenden modal-Handler nötig.
        scn[_CYCLE_LOCK_KEY] = False


def _cycle_step(context: bpy.types.Context) -> dict:
    """Führt genau eine Phase basierend auf cycle_phase_index aus."""
    scn = context.scene
    st = _get_state(scn)
    idx = int(st.get("cycle_phase_index", 0))

    if not st.get("cycle_active", False):
        return {"status": "NOOP", "reason": "cycle_not_active"}

    if idx >= len(_CYCLE_PHASES):
        # Zyklus fertig
        st["cycle_active"] = False
        scn["tco_state"] = st
        return {"status": "DONE"}

    phase = _CYCLE_PHASES[idx]
    if phase == "DETECT":
        # Phase 1: Marker-Detection am Ziel-Frame (modular, separater Helper)
        res = run_detect_once(context, start_frame=st.get("cycle_target_frame"))
        st["cycle_last_result"] = res
        st["cycle_phase_index"] = idx + 1
        scn["tco_state"] = st
        # Bei Erweiterung: Hier könnte in Folgeschritten (BIDIR, Cleanup, usw.) weiter verzweigt werden.
        return {"status": "OK", "phase": phase, "result": res}

    # Unbekannte Phase (zukunftssicherer Fallback)
    st["cycle_phase_index"] = idx + 1
    scn["tco_state"] = st
    return {"status": "OK", "phase": phase, "result": None}


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

        # --- Direkt im Anschluss Low-Marker-Frame suchen ---
        try:
            res_low = run_find_low_marker_frame(context)
            if res_low.get("status") == "FOUND":
                frame = res_low.get("frame")
                self.report({'INFO'}, f"Low-marker frame gefunden: {frame}")
                # --- Playhead auf Frame setzen ---
                res_jump = run_jump_to_frame(context, frame=frame, repeat_map={})
                if res_jump.get("status") == "OK":
                    self.report({'INFO'}, f"Playhead gesetzt auf Frame {res_jump.get('frame')}")
                    # --- Direkt danach: modularen Zyklus starten (Phase 1 = DETECT) ---
                    try:
                        cyc = _cycle_begin(context, target_frame=res_jump.get("frame"))
                        status = cyc.get("status")
                        if status in {"OK", "DONE"}:
                            # Transparente, aber knappe Operator-Meldung
                            last = (_get_state(context.scene).get("cycle_last_result") or {})
                            self.report({'INFO'}, f"Cycle gestartet → Phase DETECT: {last.get('status', 'n/a')}, new_tracks={last.get('new_tracks', 0)}")
                        else:
                            self.report({'WARNING'}, f"Cycle wurde übersprungen: {cyc}")
                    except Exception as cyc_exc:
                        self.report({'ERROR'}, f"Cycle-Start fehlgeschlagen: {cyc_exc}")
                else:
                    self.report({'WARNING'}, f"Jump failed: {res_jump}")
            else:
                self.report({'INFO'}, f"Kein Low-marker frame gefunden: {res_low}")
        except Exception as exc:
            self.report({'ERROR'}, f"Helper call failed: {exc}")

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
