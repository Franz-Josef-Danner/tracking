# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Orchestrator-Zyklus (find → jump → detect → bidi)
- Beim Auslösen: zuerst Bootstrap/Reset, dann modaler Ablauf bis Abschluss.
- Timer-start robust (auch ohne context.window).
- Konfliktfrei: es läuft immer nur eine Phase gleichzeitig.
"""

from __future__ import annotations
import bpy
from typing import Dict, Optional

# ------------------------------------------------------------
# Robuste Importe der Helper (funktionieren als Paket- oder Flat-Layout)
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# Scene Keys & Phasen
# ------------------------------------------------------------
K_CYCLE_ACTIVE   = "tco_cycle_active"
K_PHASE          = "tco_phase"
K_LAST           = "tco_last"        # letzter Step-Rückgabedatensatz (für UI/Debug)
K_GOTO_FRAME     = "goto_frame"      # Ziel-Frame für Jump
K_BIDI_ACTIVE    = "bidi_active"     # vom Bidi-Operator gesetzt/gelöscht
K_BIDI_RESULT    = "bidi_result"     # vom Bidi-Operator gesetzt
K_DETECT_LOCK    = "__detect_lock"   # von detect.py intern verwendet, hier nur respektiert

PH_FIND   = "FIND_LOW"
PH_JUMP   = "JUMP"
PH_DETECT = "DETECT"
PH_BIDI_S = "BIDI_START"
PH_BIDI_W = "BIDI_WAIT"
PH_FIN    = "FINISH"

# Timer-Intervall des Modal-Handlers (Sekunden)
TIMER_SEC = 0.20

__all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")


# ------------------------------------------------------------
# Bootstrap (intern) – setzt den Startzustand für den Zyklus
# ------------------------------------------------------------
def _bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene
    scn[K_CYCLE_ACTIVE] = True
    scn[K_PHASE] = PH_FIND
    scn[K_LAST] = {"phase": "BOOTSTRAP", "status": "OK"}
    scn.pop(K_GOTO_FRAME, None)
    scn.pop(K_BIDI_RESULT, None)
    scn[K_BIDI_ACTIVE] = False


# Öffentlicher Wrapper – falls andere Module `bootstrap(context)` importieren
def bootstrap(context: bpy.types.Context) -> None:
    _bootstrap(context)


# ------------------------------------------------------------
# Operator – startet Bootstrap und dann den modalen Orchestrator
# ------------------------------------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking-Zyklus koordinieren (find→jump→detect→bidi)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator starten"
    bl_options = {"REGISTER", "UNDO"}

    _timer: Optional[object] = None
    _repeat_map: Dict[int, int] = {}  # lokale Wiederholungs-Map für Jumps (optional)

    # ---------- Utility: Timer robust starten ----------
    def _start_timer(self, context: bpy.types.Context) -> None:
        wm = context.window_manager
        win = getattr(context, "window", None)

        # Fallbacks, wenn context.window None (z. B. Aufruf aus Preferences)
        if win is None:
            win = getattr(bpy.context, "window", None)
        if win is None:
            wins = getattr(wm, "windows", None)
            if wins and len(wins) > 0:
                win = wins[0]

        # Timer an Window binden, wenn vorhanden; sonst globaler Timer (window=None)
        try:
            self._timer = wm.event_timer_add(TIMER_SEC, window=win)
        except Exception:
            # letzte Eskalationsstufe: ohne Window
            self._timer = wm.event_timer_add(TIMER_SEC, window=None)

        wm.modal_handler_add(self)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context is not None and context.scene is not None

    def execute(self, context: bpy.types.Context):
        # 1) Sofortiger Bootstrap/Reset
        bootstrap(context)
        self.report({'INFO'}, "Bootstrap ausgeführt")

        # 2) Modal-Zyklus starten (robust, auch ohne aktives Window)
        try:
            self._start_timer(context)
        except Exception as ex:
            # Harte Absicherung: ohne Timer kein Modal → abbrechen
            context.scene[K_LAST] = {"phase": "TIMER_START", "status": "FAILED", "reason": str(ex)}
            self.report({'ERROR'}, f"Coordinator: Timer-Start fehlgeschlagen: {ex}")
            return {'CANCELLED'}

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

        scn = context.scene if context and context.scene else None
        if not scn:
            return self._finish(context)

        if not scn.get(K_CYCLE_ACTIVE, False):
            return self._finish(context)

        phase = scn.get(K_PHASE, PH_FIND)

        # -----------------------------
        # PHASE: FIND_LOW
        # -----------------------------
        if phase == PH_FIND:
            res = run_find_low_marker_frame(context)
            scn[K_LAST] = {"phase": PH_FIND, **res}

            st = res.get("status")
            if st == "FOUND":
                scn[K_GOTO_FRAME] = int(res["frame"])
                scn[K_PHASE] = PH_JUMP
            elif st == "NONE":
                scn[K_PHASE] = PH_FIN
            else:  # "FAILED" o.ä.
                scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        # -----------------------------
        # PHASE: JUMP
        # -----------------------------
        if phase == PH_JUMP:
            res = run_jump_to_frame(context, frame=scn.get(K_GOTO_FRAME), repeat_map=self._repeat_map)
            scn[K_LAST] = {"phase": PH_JUMP, **res}
            scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        # -----------------------------
        # PHASE: DETECT
        # -----------------------------
        if phase == PH_DETECT:
            # detect.py kann intern einen Lock setzen → wir warten dann einen Tick
            if scn.get(K_DETECT_LOCK, False):
                return {'RUNNING_MODAL'}

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

        # -----------------------------
        # PHASE: BIDI_START
        # -----------------------------
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

        # -----------------------------
        # PHASE: BIDI_WAIT
        # -----------------------------
        if phase == PH_BIDI_W:
            if scn.get(K_BIDI_ACTIVE, False):
                return {'RUNNING_MODAL'}
            scn[K_LAST] = {"phase": PH_BIDI_W, "bidi_result": scn.get(K_BIDI_RESULT, "")}
            scn[K_PHASE] = PH_FIND
            return {'RUNNING_MODAL'}

        # -----------------------------
        # PHASE: FINISH
        # -----------------------------
        if phase == PH_FIN:
            return self._finish(context)

        # Fallback: unbekannte Phase → neu starten bei FIND
        scn[K_PHASE] = PH_FIND
        return {'RUNNING_MODAL'}

    def _finish(self, context: bpy.types.Context):
        self._cleanup(context)
        self.report({'INFO'}, "Coordinator beendet.")
        return {'FINISHED'}


# ------------------------------------------------------------
# Registrierung
# ------------------------------------------------------------
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
