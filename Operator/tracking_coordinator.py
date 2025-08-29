# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Orchestrator-Zyklus (find → jump → detect → bidi)
- Start via Operator-Button (CLIP_EDITOR).
- Modal gesteuerte, konfliktfreie Sequenz mit Scene-Flags.
"""

from __future__ import annotations
import bpy
import time
from typing import Dict, Any, Optional

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

# CLIP_OT_bidirectional_track ist ein Operator – wir rufen ihn über bpy.ops auf.
# (Er setzt scene["bidi_active"]/["bidi_result"] selbst.) filecite: turn0file0 

# -------------------------
# Scene Keys
# -------------------------
K_CYCLE_ACTIVE   = "tco_cycle_active"
K_PHASE          = "tco_phase"
K_LAST           = "tco_last"            # letzter Rückgabedatensatz (Dict)
K_REPEAT_MAP     = "tco_repeat_map"      # (nur Info; echte Map lebt im Operator-Kontext)
K_GOTO_FRAME     = "goto_frame"          # von jump_to_frame respektiert
K_BIDI_ACTIVE    = "bidi_active"         # gesetzt von CLIP_OT_bidirectional_track
K_BIDI_RESULT    = "bidi_result"         # gesetzt von CLIP_OT_bidirectional_track
K_DETECT_LOCK    = "__detect_lock"       # gesetzt in Helper/detect.py :contentReference[oaicite:3]{index=3}

PH_FIND   = "FIND_LOW"
PH_JUMP   = "JUMP"
PH_DETECT = "DETECT"
PH_BIDI_S = "BIDI_START"
PH_BIDI_W = "BIDI_WAIT"
PH_FIN    = "FINISH"

TIMER_SEC = 0.20

# -------------------------
# Bootstrap
# -------------------------
def _bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene
    scn[K_CYCLE_ACTIVE] = True
    scn[K_PHASE] = PH_FIND
    scn[K_LAST] = {}
    scn.pop(K_GOTO_FRAME, None)
    scn.pop(K_BIDI_RESULT, None)
    scn[K_BIDI_ACTIVE] = False

# -------------------------
# Operator
# -------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking-Zyklus koordinieren (find→jump→detect→bidi)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator starten"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _repeat_map: Dict[int, int] = {}  # lokale Jump-Wiederholungen

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

    def cancel(self, context):
        self._cleanup(context)

    def _cleanup(self, context):
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

        # ---- PHASE: FIND_LOW ----
        if phase == PH_FIND:
            res = run_find_low_marker_frame(context)  # :contentReference[oaicite:4]{index=4}
            scn[K_LAST] = {"phase": PH_FIND, **res}
            st = res.get("status")
            if st == "FOUND":
                frame = int(res["frame"])
                scn[K_GOTO_FRAME] = frame
                scn[K_PHASE] = PH_JUMP
                return {'RUNNING_MODAL'}
            elif st == "NONE":
                scn[K_PHASE] = PH_FIN
                return {'RUNNING_MODAL'}
            else:
                # FAILED → trotzdem weiter mit DETECT, um evtl. Basis zu erhöhen
                scn[K_PHASE] = PH_DETECT
                return {'RUNNING_MODAL'}

        # ---- PHASE: JUMP ----
        if phase == PH_JUMP:
            # repeat_map intern führen; jump_to_frame kann eine Map annehmen
            res = run_jump_to_frame(context, frame=scn.get(K_GOTO_FRAME), repeat_map=self._repeat_map)  # :contentReference[oaicite:5]{index=5}
            scn[K_LAST] = {"phase": PH_JUMP, **res}
            if res.get("status") == "OK":
                scn[K_PHASE] = PH_DETECT
            else:
                # Jump fehlgeschlagen → trotzdem DETECT versuchen (robust)
                scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        # ---- PHASE: DETECT (synchron, aber mit internem Lock) ----
        if phase == PH_DETECT:
            # Wenn detect-lock aktiv ist (asynchroner Konflikt), warten wir 1 Tick.
            if scn.get(K_DETECT_LOCK, False):
                return {'RUNNING_MODAL'}
            # Adaptive Detect am aktuellen Frame
            res = run_detect_adaptive(
                context,
                start_frame=None,
                max_attempts=4,
                selection_policy="only_new",
                duplicate_strategy="delete",
                post_pattern_triplet=True,
            )  # :contentReference[oaicite:6]{index=6}
            scn[K_LAST] = {"phase": PH_DETECT, **res}
            st = res.get("status")
            if st == "FAILED":
                # Bei FAIL direkt Bidi laufen lassen → evtl. schließen Tracks Lücken
                scn[K_PHASE] = PH_BIDI_S
            else:
                # READY / RUNNING (RUNNING wird intern in detect adaptiert, hier ein Pass pro Tick)
                scn[K_PHASE] = PH_BIDI_S
            return {'RUNNING_MODAL'}

        # ---- PHASE: BIDI_START → Operator starten, dann WAIT ----
        if phase == PH_BIDI_S:
            if scn.get(K_BIDI_ACTIVE, False):
                # Bidi läuft bereits (z. B. manuell gestartet) → warten
                scn[K_PHASE] = PH_BIDI_W
                return {'RUNNING_MODAL'}
            # Operator starten (UI-Kontext wird im Operator intern gehandhabt)
            try:
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')  # startet modal und setzt Flags :contentReference[oaicite:7]{index=7}
                scn[K_PHASE] = PH_BIDI_W
            except Exception as ex:
                scn[K_LAST] = {"phase": PH_BIDI_S, "status": "FAILED", "reason": str(ex)}
                # Wenn Bidi nicht startet, zur Sicherheit direkt weiter zum nächsten FIND
                scn[K_PHASE] = PH_FIND
            return {'RUNNING_MODAL'}

        # ---- PHASE: BIDI_WAIT → bis bidi_active False ----
        if phase == PH_BIDI_W:
            if scn.get(K_BIDI_ACTIVE, False):
                return {'RUNNING_MODAL'}  # weiter warten
            # Fertig → Ergebnis prüfen, dann NÄCHSTER Zyklus (FIND)
            result = scn.get(K_BIDI_RESULT, "")
            scn[K_LAST] = {"phase": PH_BIDI_W, "bidi_result": result}
            scn[K_PHASE] = PH_FIND
            return {'RUNNING_MODAL'}

        # ---- PHASE: FINISH ----
        if phase == PH_FIN:
            return self._finish(context)

        # Fallback
        scn[K_PHASE] = PH_FIND
        return {'RUNNING_MODAL'}

    def _finish(self, context):
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
