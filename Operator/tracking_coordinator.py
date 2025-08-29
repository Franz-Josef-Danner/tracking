# a/Operator/tracking_coordinator.py


from __future__ import annotations
import bpy
from typing import Dict, Optional, Tuple

print(f"[Coordinator] LOADED from {__file__}")

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
    from ..Helper.detect import run_detect_once
except Exception:
    from Helper.detect import run_detect_once  # type: ignore

try:
    from ..Helper.clean_short_tracks import clean_short_tracks
except Exception:
    from Helper.clean_short_tracks import clean_short_tracks  # type: ignore

try:
    from ..Helper.spike_filter_cycle import run_marker_spike_filter_cycle
except Exception:
    from Helper.spike_filter_cycle import run_marker_spike_filter_cycle  # type: ignore

try:
    from ..Helper.find_max_marker_frame import run_find_max_marker_frame
except Exception:
    from Helper.find_max_marker_frame import run_find_max_marker_frame  # type: ignore

# ------------------------------------------------------------
# Utility
# ------------------------------------------------------------
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
PH_SPIKE  = "SPIKE_FILTER"           # NEU: Second-Cycle Step 1
PH_FMAX   = "FIND_MAX_MARKER"        # NEU: Second-Cycle Step 2

# Error-Threshold-State (für Second-Cycle)
K_ERR_THR_BASE = "tco_err_thr_base"  # ursprünglicher Basiswert (Reset bei Rückkehr zu Cycle 1)
K_ERR_THR_CURR = "tco_err_thr_curr"  # aktueller Arbeitswert (wird *0.9 gesenkt)
ERR_THR_FLOOR  = 10.0                # px, Abbruch-Schwelle Second-Cycle

def _get_err_threshold_pair(scn: bpy.types.Scene) -> Tuple[float, float]:
    return float(scn.get(K_ERR_THR_BASE, 0.0) or  float(scn.get("error_threshold_px", 100.0))), float(scn.get(K_ERR_THR_CURR, 0.0) or float(scn.get("error_threshold_px", 100.0)))
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
    # Error-Threshold-Initialisierung (Second-Cycle)
    try:
        base = float(scn.get("error_threshold_px", 100.0))
    except Exception:
        base = 100.0
    scn[K_ERR_THR_BASE] = base
    scn[K_ERR_THR_CURR] = base
    # Hinweis im Last-Log
    scn[K_LAST].update({"err_thr_base": base})

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

    def _dbg(self, context, msg: str):
        try:
            print(f"[Coordinator] {msg}")
            context.scene[K_LAST] = {"phase": context.scene.get(K_PHASE, "N/A"),
                                     "msg": msg,
                                     "tick": int(context.scene.get("__tco_ticks", 0))}
        except Exception:
            pass

    # --- robuste Window-Wahl (lokal, unabhängig von externen Utils) ---
    def _pick_window_for_timer(self, context):
        wm = getattr(context, "window_manager", None) or bpy.context.window_manager
        win = getattr(context, "window", None)
        if win:
            return win
        wins = list(getattr(wm, "windows", [])) if wm else []
        # bevorzugt ein Window mit CLIP_EDITOR
        for w in wins:
            try:
                if w.screen:
                    for a in w.screen.areas:
                        if a.type == 'CLIP_EDITOR':
                            return w
            except Exception:
                continue
        return wins[0] if wins else None

    def _start_timer(self, context):
        wm = getattr(context, "window_manager", None) or bpy.context.window_manager
        scn = context.scene
        self._timer = None
        paths = []  # <-- zuerst initialisieren
    
        win = self._pick_window_for_timer(context)
        if wm and win:
            try:
                self._timer = wm.event_timer_add(TIMER_SEC, window=win)
                paths.append("event_timer_add(window=clip_editor)")
            except Exception as ex:
                paths.append(f"event_timer_add(window=clip_editor) FAILED: {ex}")
    
        if not self._timer and wm:
            try:
                self._timer = wm.event_timer_add(TIMER_SEC)
                paths.append("event_timer_add(global)")
            except Exception as ex:
                paths.append(f"event_timer_add(global) FAILED: {ex}")
                try:
                    self._timer = wm.event_timer_add(TIMER_SEC, window=None)
                    paths.append("event_timer_add(window=None)")
                except Exception as ex2:
                    paths.append(f"event_timer_add(window=None) FAILED: {ex2}")
    
        scn[K_LAST] = {"phase": "TIMER_START",
                       "status": "OK" if self._timer else "FAILED",
                       "paths": paths}
        print(f"[Coordinator] _start_timer → {scn[K_LAST]}")
        self.report({'INFO'}, f"Timer status={'OK' if self._timer else 'FAILED'} paths={paths}")
    
        if not self._timer:
            raise RuntimeError(f"Timer konnte nicht erstellt werden. paths={paths}")
    
        wm.modal_handler_add(self)
        self._dbg(context, "modal_handler_add() registered")


    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        ok = bool(context and getattr(context, "scene", None))
        # Optionales Poll-Log (einmalig):
        # print(f"[Coordinator] poll → {ok}")
        return ok

    def invoke(self, context, event):
        bootstrap(context)
        self.report({'INFO'}, "Coordinator invoke → Bootstrap OK")
        try:
            self._start_timer(context)
        except Exception as ex:
            context.scene[K_LAST] = {"phase": "TIMER_START", "status": "FAILED", "reason": str(ex)}
            self.report({'ERROR'}, f"Coordinator: Timer-Start FAILED: {ex}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator invoke → Timer running")
        return {'RUNNING_MODAL'}

    def execute(self, context):
        bootstrap(context)
        self.report({'INFO'}, "Coordinator execute → Bootstrap OK")
        try:
            self._start_timer(context)
        except Exception as ex:
            context.scene[K_LAST] = {"phase": "TIMER_START", "status": "FAILED", "reason": str(ex)}
            self.report({'ERROR'}, f"Coordinator: Timer-Start FAILED: {ex}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator execute → Timer running")
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
        self._dbg(context, "cleanup done")

    def modal(self, context: bpy.types.Context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scn = context.scene if context and context.scene else None
        if not scn:
            self._dbg(context, "modal: no scene → finish")
            return self._finish(context)

        # TICK-Log
        scn["__tco_ticks"] = int(scn.get("__tco_ticks", 0)) + 1
        tick = scn["__tco_ticks"]
        print(f"[Coordinator] TIMER tick #{tick}, phase={scn.get(K_PHASE, PH_FIND)}")

        if not scn.get(K_CYCLE_ACTIVE, False):
            self._dbg(context, "cycle inactive → finish")
            return self._finish(context)

        phase = scn.get(K_PHASE, PH_FIND)

        if phase == PH_FIND:
            res = run_find_low_marker_frame(context)
            scn[K_LAST] = {"phase": PH_FIND, **res, "tick": tick}
            print(f"[Coordinator] FIND_LOW → {res}")
            st = res.get("status")
            if st == "FOUND":
                scn[K_GOTO_FRAME] = int(res["frame"])
                scn[K_PHASE] = PH_JUMP
            elif st == "NONE":
                # → Second-Cycle starten
                # Hinweis: Threshold wird im Second-Cycle geführt (K_ERR_THR_CURR)
                base, curr = _get_err_threshold_pair(scn)
                scn[K_LAST] = {"phase": PH_FIND, "status": "NONE", "err_thr_curr": curr, "tick": tick}
                scn[K_PHASE] = PH_SPIKE
            else:
                scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        if phase == PH_JUMP:
            res = run_jump_to_frame(context, frame=scn.get(K_GOTO_FRAME), repeat_map=self._repeat_map)
            scn[K_LAST] = {"phase": PH_JUMP, **res, "tick": tick}
            print(f"[Coordinator] JUMP → {res}")
            scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        if phase == PH_DETECT:
            if scn.get(K_DETECT_LOCK, False):
                print("[Coordinator] DETECT locked → wait")
                return {'RUNNING_MODAL'}
                
        if phase == PH_SPIKE:
            # Second-Cycle Step 1: Spike-Filter mit aktuellem Threshold
            _, curr = _get_err_threshold_pair(scn)
            try:
                sres = run_marker_spike_filter_cycle(context, track_threshold=float(curr))
                scn[K_LAST] = {"phase": PH_SPIKE, **sres, "err_thr_used": float(curr), "tick": tick}
                print(f"[Coordinator] SPIKE_FILTER(thr={curr}) → {sres}")
            except Exception as ex:
                scn[K_LAST] = {"phase": PH_SPIKE, "status": "FAILED", "reason": str(ex), "err_thr_used": float(curr), "tick": tick}
                print(f"[Coordinator] SPIKE_FILTER FAILED → {ex}")
            scn[K_PHASE] = PH_FMAX
            return {'RUNNING_MODAL'}

        if phase == PH_FMAX:
            # Second-Cycle Step 2: Max-Marker-Frame suchen
            fmr = run_find_max_marker_frame(context, log_each_frame=False, return_observed_min=True)
            scn[K_LAST] = {"phase": PH_FMAX, **fmr, "tick": tick}
            print(f"[Coordinator] FIND_MAX_MARKER → {fmr}")
            if fmr.get("status") == "FOUND":
                # → zurück in Cycle 1 und Error-Threshold resetten
                scn[K_ERR_THR_CURR] = float(scn.get(K_ERR_THR_BASE, scn.get("error_threshold_px", 100.0)))
                scn[K_PHASE] = PH_FIND
                return {'RUNNING_MODAL'}
            # Kein Frame gefunden → Threshold senken (*0.9), Floor 10 px
            try:
                curr = float(scn.get(K_ERR_THR_CURR, scn.get("error_threshold_px", 100.0)))
            except Exception:
                curr = float(scn.get("error_threshold_px", 100.0))
            next_thr = max(ERR_THR_FLOOR, curr * 0.9)
            scn[K_ERR_THR_CURR] = float(next_thr)
            scn[K_LAST].update({"err_thr_curr_next": float(next_thr)})
            # Wenn Floor erreicht → Second-Cycle fertig → Gesamtprozess beenden
            if next_thr <= ERR_THR_FLOOR + 1e-6:
                print("[Coordinator] Second-Cycle beendet: Threshold-Floor erreicht")
                scn[K_PHASE] = PH_FIN
            else:
                # → erneut Spike-Filter laufen lassen
                scn[K_PHASE] = PH_SPIKE
            return {'RUNNING_MODAL'}

            # Zentrales Wiederholungslimit (UI/Scene-property override-bar)
            max_attempts = int(scn.get("detect_max_attempts", 20))
        
            res = {}
            start_frame = None
            for attempt in range(max_attempts):
                res = run_detect_once(
                    context,
                    start_frame=start_frame,
                    selection_policy="only_new",
                    duplicate_strategy="delete",
                    post_pattern_triplet=True,
                )
                st = res.get("status")
                scn[K_LAST] = {"phase": PH_DETECT, **res, "attempt": attempt + 1, "tick": tick}
                print(f"[Coordinator] DETECT attempt {attempt+1}/{max_attempts} → {res}")
                if st in ("READY", "FAILED"):
                    break
                start_frame = res.get("frame", start_frame)
        
            scn[K_PHASE] = PH_BIDI_S
            return {'RUNNING_MODAL'}
        
        if phase == PH_BIDI_S:
            # Falls Bidi bereits aktiv ist, direkt in die Wait-Phase
            if scn.get(K_BIDI_ACTIVE, False):
                scn[K_PHASE] = PH_BIDI_W
                return {'RUNNING_MODAL'}
            try:
                # Start: Bidirectional Track Operator auslösen
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                scn[K_PHASE] = PH_BIDI_W
                print("[Coordinator] BIDI_START → invoked")
            except Exception as ex:
                # Fallback: zurück in FIND, wenn Operator nicht verfügbar/fehlgeschlagen
                scn[K_LAST] = {"phase": PH_BIDI_S, "status": "FAILED", "reason": str(ex), "tick": tick}
                print(f"[Coordinator] BIDI_START FAILED → {ex}")
                scn[K_PHASE] = PH_FIND
            return {'RUNNING_MODAL'}

        if phase == PH_BIDI_W:
            if scn.get(K_BIDI_ACTIVE, False):
                return {'RUNNING_MODAL'}
            scn[K_LAST] = {"phase": PH_BIDI_W, "bidi_result": scn.get(K_BIDI_RESULT, ""), "tick": tick}
            print(f"[Coordinator] BIDI_WAIT → done: {scn.get(K_BIDI_RESULT, '')}")
            
            # --- NEU: Short-Track-Cleaner nach Bidi ---
            try:
                processed, affected = clean_short_tracks(context)
                print(f"[Coordinator] CLEAN_SHORT → processed={processed}, affected={affected}")
            except Exception as ex:
                print(f"[Coordinator] CLEAN_SHORT FAILED → {ex}")
            # **WICHTIG**: Bei Rückkehr in Cycle 1 immer Error-Threshold resetten
            try:
                scn[K_ERR_THR_CURR] = float(scn.get(K_ERR_THR_BASE, scn.get("error_threshold_px", 100.0)))
            except Exception:
                scn[K_ERR_THR_CURR] = float(scn.get("error_threshold_px", 100.0))
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
    print(f"[Coordinator] unregister() from {__file__}")
    try:
        bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
