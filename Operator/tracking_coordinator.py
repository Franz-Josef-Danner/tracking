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

# --- NEU: Utility zum robusten Finden eines Windows (bevor _start_timer) ---
def _pick_window_for_timer(context: bpy.types.Context) -> Optional[bpy.types.Window]:
    wm = context.window_manager if getattr(context, "window_manager", None) else bpy.context.window_manager
    # 1) Bevorzugt: aktuelles Window aus context
    win = getattr(context, "window", None)
    if win:
        return win

    # 2) Bevorzugt: Ein Window, das einen CLIP_EDITOR hat
    wins = list(getattr(wm, "windows", [])) if wm else []
    for w in wins:
        try:
            scr = w.screen
            if not scr:
                continue
            for area in scr.areas:
                if area.type == 'CLIP_EDITOR':
                    return w
        except Exception:
            continue

    # 3) Fallback: Irgendein Window
    if wins:
        return wins[0]

    # 4) Nichts gefunden
    return None


# --- PATCH: _start_timer ersetzt ---
def _start_timer(self, context: bpy.types.Context) -> None:
    wm = context.window_manager if getattr(context, "window_manager", None) else bpy.context.window_manager
    scn = context.scene

    # A) Versuche gezielt ein Window mit CLIP_EDITOR zu bekommen
    win = _pick_window_for_timer(context)
    try_paths = []

    # Pfad 1: Timer an gefundenes Window hängen
    if wm and win:
        try:
            self._timer = wm.event_timer_add(TIMER_SEC, window=win)
            try_paths.append("window=clip_editor")
        except Exception as ex:
            try_paths.append(f"window=clip_editor_failed:{ex}")

    # Pfad 2: Timer ohne Window (global)
    if not self._timer and wm:
        try:
            # manche Builds mögen das explizite keyword nicht → ohne kw probieren
            self._timer = wm.event_timer_add(TIMER_SEC)
            try_paths.append("window=global_no_kw")
        except Exception as ex:
            try_paths.append(f"global_no_kw_failed:{ex}")
            # letzte Eskalation: explizit window=None
            try:
                self._timer = wm.event_timer_add(TIMER_SEC, window=None)
                try_paths.append("window=None_kw")
            except Exception as ex2:
                try_paths.append(f"window=None_kw_failed:{ex2}")

    # Ergebnis protokollieren
    scn[K_LAST] = {"phase": "TIMER_START", "status": "OK" if self._timer else "FAILED", "paths": try_paths}

    if not self._timer:
        raise RuntimeError(f"event_timer_add failed via paths={try_paths}")

    wm.modal_handler_add(self)


# --- NEU: invoke() hinzufügen, damit Button-Klick den korrekten Pfad nutzt ---
def invoke(self, context, event):
    # Direkt hier bootstrap + timer; UI triggert üblicherweise invoke()
    bootstrap(context)
    self.report({'INFO'}, "Bootstrap ausgeführt (invoke)")
    try:
        self._start_timer(context)
    except Exception as ex:
        context.scene[K_LAST] = {"phase": "TIMER_START", "status": "FAILED", "reason": str(ex)}
        self.report({'ERROR'}, f"Coordinator: Timer-Start fehlgeschlagen: {ex}")
        return {'CANCELLED'}
    return {'RUNNING_MODAL'}


# --- execute() leicht anpassen, falls jemand per Script aufruft ---
def execute(self, context):
    bootstrap(context)
    self.report({'INFO'}, "Bootstrap ausgeführt (execute)")
    try:
        self._start_timer(context)
    except Exception as ex:
        context.scene[K_LAST] = {"phase": "TIMER_START", "status": "FAILED", "reason": str(ex)}
        self.report({'ERROR'}, f"Coordinator: Timer-Start fehlgeschlagen: {ex}")
        return {'CANCELLED'}
    return {'RUNNING_MODAL'}

# ------------------------------------------------------------
# Operator – startet Bootstrap und dann den modalen Orchestrator
# ------------------------------------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking-Zyklus koordinieren (find→jump→detect→bidi)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator starten"
    bl_options = {"REGISTER", "UNDO"}

    _timer: Optional[object] = None
    _repeat_map: Dict[int, int] = {}

    # --- robuste Window-Wahl (nutzt deine Top-Level-Hilfsfunktion) ---
    def _pick_window_for_timer(self, context):
        try:
            return _pick_window_for_timer(context)  # nutzt die oben definierte Utility
        except Exception:
            return None

    # --- KLASSEN-Methode: robuster Timer-Start + Logging ---
    def _start_timer(self, context: bpy.types.Context) -> None:
        wm = context.window_manager if getattr(context, "window_manager", None) else bpy.context.window_manager
        scn = context.scene
        try_paths = []
        self._timer = None

        win = self._pick_window_for_timer(context)

        if wm and win:
            try:
                self._timer = wm.event_timer_add(TIMER_SEC, window=win)
                try_paths.append("window=clip_editor")
            except Exception as ex:
                try_paths.append(f"window=clip_editor_failed:{ex}")

        if not self._timer and wm:
            try:
                self._timer = wm.event_timer_add(TIMER_SEC)
                try_paths.append("window=global_no_kw")
            except Exception as ex:
                try_paths.append(f"global_no_kw_failed:{ex}")
                try:
                    self._timer = wm.event_timer_add(TIMER_SEC, window=None)
                    try_paths.append("window=None_kw")
                except Exception as ex2:
                    try_paths.append(f"window=None_kw_failed:{ex2}")

        scn[K_LAST] = {"phase": "TIMER_START", "status": "OK" if self._timer else "FAILED", "paths": try_paths}
        print(f"[Coordinator] _start_timer → {scn[K_LAST]}")

        if not self._timer:
            raise RuntimeError(f"event_timer_add failed via paths={try_paths}")

        wm.modal_handler_add(self)

    # --- invoke(): UI-Flow (Button) ---
    def invoke(self, context, event):
        bootstrap(context)
        self.report({'INFO'}, "Bootstrap ausgeführt (invoke)")
        try:
            self._start_timer(context)
        except Exception as ex:
            context.scene[K_LAST] = {"phase": "TIMER_START", "status": "FAILED", "reason": str(ex)}
            self.report({'ERROR'}, f"Coordinator: Timer-Start fehlgeschlagen: {ex}")
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    # --- execute(): Script-Flow (falls ohne invoke aufgerufen) ---
    def execute(self, context: bpy.types.Context):
        bootstrap(context)
        self.report({'INFO'}, "Bootstrap ausgeführt (execute)")
        try:
            self._start_timer(context)
        except Exception as ex:
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
        # --- Diagnose: kommen TIMER-Events überhaupt? ---
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scn = context.scene if context and context.scene else None
        if not scn:
            print("[Coordinator] modal: no scene → finish")
            return self._finish(context)

        # TICK-Log
        tick_ctr = int(scn.get("__tco_ticks", 0)) + 1
        scn["__tco_ticks"] = tick_ctr
        scn[K_LAST] = {"phase": scn.get(K_PHASE, PH_FIND), "tick": tick_ctr}
        # print kann zur Not auskommentiert werden
        print(f"[Coordinator] TIMER tick #{tick_ctr}, phase={scn.get(K_PHASE, PH_FIND)}")

        if not scn.get(K_CYCLE_ACTIVE, False):
            print("[Coordinator] cycle inactive → finish")
            return self._finish(context)

        phase = scn.get(K_PHASE, PH_FIND)

        if phase == PH_FIND:
            res = run_find_low_marker_frame(context)
            scn[K_LAST] = {"phase": PH_FIND, **res, "tick": tick_ctr}
            print(f"[Coordinator] FIND_LOW → {res}")
            st = res.get("status")
            if st == "FOUND":
                scn[K_GOTO_FRAME] = int(res["frame"])
                scn[K_PHASE] = PH_JUMP
            elif st == "NONE":
                scn[K_PHASE] = PH_FIN
            else:
                scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        if phase == PH_JUMP:
            res = run_jump_to_frame(context, frame=scn.get(K_GOTO_FRAME), repeat_map=self._repeat_map)
            scn[K_LAST] = {"phase": PH_JUMP, **res, "tick": tick_ctr}
            print(f"[Coordinator] JUMP → {res}")
            scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        if phase == PH_DETECT:
            if scn.get(K_DETECT_LOCK, False):
                print("[Coordinator] DETECT locked → wait")
                return {'RUNNING_MODAL'}

            res = run_detect_adaptive(context,
                                      start_frame=None,
                                      max_attempts=4,
                                      selection_policy="only_new",
                                      duplicate_strategy="delete",
                                      post_pattern_triplet=True)
            scn[K_LAST] = {"phase": PH_DETECT, **res, "tick": tick_ctr}
            print(f"[Coordinator] DETECT → {res}")
            scn[K_PHASE] = PH_BIDI_S
            return {'RUNNING_MODAL'}

        if phase == PH_BIDI_S:
            if scn.get(K_BIDI_ACTIVE, False):
                scn[K_PHASE] = PH_BIDI_W
                return {'RUNNING_MODAL'}
            try:
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                scn[K_PHASE] = PH_BIDI_W
                print("[Coordinator] BIDI_START → invoked")
            except Exception as ex:
                scn[K_LAST] = {"phase": PH_BIDI_S, "status": "FAILED", "reason": str(ex), "tick": tick_ctr}
                print(f"[Coordinator] BIDI_START FAILED → {ex}")
                scn[K_PHASE] = PH_FIND
            return {'RUNNING_MODAL'}

        if phase == PH_BIDI_W:
            if scn.get(K_BIDI_ACTIVE, False):
                return {'RUNNING_MODAL'}
            scn[K_LAST] = {"phase": PH_BIDI_W, "bidi_result": scn.get(K_BIDI_RESULT, ""), "tick": tick_ctr}
            print(f"[Coordinator] BIDI_WAIT → done: {scn.get(K_BIDI_RESULT, '')}")
            scn[K_PHASE] = PH_FIND
            return {'RUNNING_MODAL'}

        if phase == PH_FIN:
            print("[Coordinator] FINISH")
            return self._finish(context)

        scn[K_PHASE] = PH_FIND
        print("[Coordinator] unknown phase → reset to FIND")
        return {'RUNNING_MODAL'}

    def _finish(self, context: bpy.types.Context):
        self._cleanup(context)
        self.report({'INFO'}, "Coordinator beendet.")
        print("[Coordinator] FINISHED")
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
