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

from ..Helper.detect import run_detect_basic
from ..Helper.count import within_band as count_within_band  # falls genutzt
from ..Helper.multi import run_multi_pass  # falls genutzt
from ..Helper.distanze import some_fn  # falls genutzt

try:
    from ..Helper.distanze import run_distance_cleanup
except Exception:
    from Helper.distanze import run_distance_cleanup  # type: ignore

try:
    from ..Helper.count import evaluate_marker_count
except Exception:
    from Helper.count import evaluate_marker_count  # type: ignore

try:
    from ..Helper.multi import run_multi_pass
except Exception:
    from Helper.multi import run_multi_pass  # type: ignore

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

try:
    from ..Helper.clean_short_segments import clean_short_segments
except Exception:
    from Helper.clean_short_segments import clean_short_segments  # type: ignore

try:
    from ..Helper.marker_adapt_helper import run_marker_adapt_boost
except Exception:
    from Helper.marker_adapt_helper import run_marker_adapt_boost  # type: ignore
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
K_DETECT_LOCK    = "tco_detect_lock" # <-- FEHLT aktuell, hier ergänzen
DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # aus detect.py

PH_FIND   = "FIND_LOW"
PH_JUMP   = "JUMP"
PH_DETECT = "DETECT"
PH_BIDI_S = "BIDI_START"
PH_BIDI_W = "BIDI_WAIT"
PH_FIN    = "FINISH"
PH_CSEG   = "CLEAN_SHORT_SEGMENTS"   # Second-Cycle (nach SPIKE)
PH_CTRK   = "CLEAN_SHORT_TRACKS"     # Second-Cycle (nach CSEG)
PH_SPIKE  = "SPIKE_FILTER"           # Second-Cycle (erster Schritt)
PH_FMAX   = "FIND_MAX_MARKER"        # Second-Cycle (nach CTRK)
# Einmaliges Init-Flag für Zyklus 2 (Select-All am Eintritt)
K_CYCLE2_INIT = "tco_cycle2_init_done"
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
# Utility: Alle Tracks im aktiven Clip selektieren
# ------------------------------------------------------------
def _select_all_tracks(context) -> int:
    try:
        # Aktiven Clip bevorzugen (CLIP_EDITOR), sonst erstes MovieClip
        space = getattr(context, "space_data", None)
        if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
            clip = space.clip
        else:
            clip = bpy.data.movieclips[0] if bpy.data.movieclips else None
        if not clip:
            return 0
        # Objekt-Tracks bevorzugen, sonst globale Tracks
        try:
            obj = clip.tracking.objects.active
            tracks = obj.tracks if (obj and getattr(obj, "tracks", None)) else None
        except Exception:
            tracks = None
        if tracks is None:
            tracks = getattr(clip.tracking, "tracks", None)
        if not tracks:
            return 0
        n = 0
        for tr in list(tracks):
            try:
                tr.select = True
                n += 1
            except Exception:
                pass
        return n
    except Exception:
        return 0


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
            # ID-Property-safe Mini-Log
            context.scene[K_LAST] = {
                "phase": str(context.scene.get(K_PHASE, "N/A")),
                "msg": str(msg),
                "tick": int(context.scene.get("__tco_ticks", 0)),
            }
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
                # EINMALIG am Anfang von Zyklus 2: alle Tracks selektieren
                if not scn.get(K_CYCLE2_INIT, False):
                    n_sel = _select_all_tracks(context)
                    scn[K_CYCLE2_INIT] = True
                    print(f"[Coordinator] CYCLE2_INIT → selected all tracks: {n_sel}")
                scn[K_PHASE] = PH_SPIKE
            else:
                scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        if phase == PH_JUMP:
            res = run_jump_to_frame(context, frame=scn.get(K_GOTO_FRAME), repeat_map=self._repeat_map)
            scn[K_LAST] = {"phase": PH_JUMP, **res, "tick": tick}
            print(f"[Coordinator] JUMP → {res}")

            # Wenn derselbe Frame mehrfach angesprungen wird → Marker Adapt Trigger
            if res.get("repeat_count", 0) > 1:
                try:
                    run_marker_adapt_boost(context)
                    print("[Coordinator] marker_adapt_boost ausgelöst")
                except Exception as ex:
                    print(f"[Coordinator] marker_adapt_boost FAILED → {ex}")

            scn[K_PHASE] = PH_DETECT
            return {'RUNNING_MODAL'}

        if phase == PH_DETECT:
            if scn.get(K_DETECT_LOCK, False):
                print("[Coordinator] DETECT locked → wait")
                return {'RUNNING_MODAL'}
            # Wiederholungslimit (Mini-Zyklus)
            max_attempts = int(scn.get("detect_max_attempts", 12))
            start_frame = None

            # Zielkorridor
            marker_target = int(scn.get("tco_marker_target", scn.get("marker_adapt", scn.get("marker_basis", 20))))
            min_marker = int(max(1, round(marker_target * 0.9)))
            max_marker = int(max(2, round(marker_target * 1.2)))
            scn["__tco_marker_target_effective"] = int(marker_target)
            close_dist_rel = float(scn.get("tco_close_dist_rel", 0.01))

            # PID-ähnliche Schwellensteuerung (ident zu bisherigem Verhalten)
            def _adjust_threshold(curr_thr: float, observed: int, target: int) -> float:
                error = (float(observed) - float(target)) / max(1.0, float(target))
                acc = float(scn.get("__thr_i", 0.0)) + error
                scn["__thr_i"] = acc
                k_p, k_i = 0.65, 0.10
                scale = 1.0 + (k_p * error + k_i * acc)
                return max(1e-4, curr_thr * scale)

            res_last = {}
            for attempt in range(1, max_attempts + 1):
                # 1) Marker setzen (Basic)
                basic = run_detect_basic(context, start_frame=start_frame, selection_policy="only_new")
                # --- ID-Property-safe Log: Sets entfernen/kompakt darstellen ---
                basic_safe = dict(basic)
                if "pre_ptrs" in basic_safe:
                    basic_safe["pre_count"] = len(basic_safe.pop("pre_ptrs") or [])
                scn[K_LAST] = {
                    "phase": PH_DETECT,
                    **{k: (int(v) if isinstance(v, bool) else v) for k, v in basic_safe.items() if k not in ("width","height")},  # keep it lean
                    "attempt": int(attempt),
                    "tick": int(tick),
                }
                print(f"[Coordinator] DETECT basic {attempt}/{max_attempts} → {basic}")
                if basic.get("status") == "FAILED":
                    break

                frame_now = int(basic.get("frame", scn.frame_current))
                pre_ptrs  = set(basic.get("pre_ptrs", set()))
                thr_now   = float(basic.get("threshold", float(scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))))

                # 2) Distanz-Cleanup (gegen pre_ptrs)
                dres = run_distance_cleanup(context, pre_ptrs=pre_ptrs, frame=frame_now, close_dist_rel=close_dist_rel)
                remaining_ptrs = {t.as_pointer() for t in bpy.context.edit_movieclip.tracking.tracks if t.as_pointer() not in pre_ptrs} if getattr(bpy.context, "edit_movieclip", None) else {t.as_pointer() for t in bpy.data.movieclips[0].tracking.tracks if t.as_pointer() not in pre_ptrs} if bpy.data.movieclips else set()

                # 3) Count-Bewertung
                cres = evaluate_marker_count(new_ptrs_after_cleanup=remaining_ptrs, min_marker=int(min_marker), max_marker=int(max_marker))
                print(f"[Coordinator] DETECT count → {cres}")
                if cres.get("status") == "ENOUGH":
                    # 4) Multi-Pass (Triplets) mit *gleichem* threshold
                    mres = run_multi_pass(context, detect_threshold=float(thr_now), pre_ptrs=pre_ptrs)
                    # 5) Finaler Distanz-Cleanup auch für Triplets
                    _ = run_distance_cleanup(context, pre_ptrs=pre_ptrs, frame=frame_now, close_dist_rel=close_dist_rel)
                    # --- ID-Property-safe Aggregation ---
                    mres_safe = dict(mres)
                    if "new_ptrs" in mres_safe:
                        mres_safe["new_count"] = len(mres_safe.pop("new_ptrs") or [])
                    res_last = {
                        "basic": {k: v for k, v in basic_safe.items()},
                        "distance": {k: v for k, v in dres.items()},
                        "count": {k: v for k, v in cres.items()},
                        "multi": {k: v for k, v in mres_safe.items()},
                    }
                    break

                # Nicht genug / zu viel → Threshold anpassen, neue Runde
                observed_n = int(cres.get("count", 0))
                new_thr = _adjust_threshold(float(thr_now), observed_n, int(marker_target))
                scn[DETECT_LAST_THRESHOLD_KEY] = float(new_thr)
                print(f"[Coordinator] DETECT adjust threshold: {thr_now} → {new_thr} (obs={observed_n}, target={marker_target})")
                start_frame = frame_now  # stabilisieren
                res_last = {
                    "basic": {k: v for k, v in basic_safe.items()},
                    "distance": {k: v for k, v in dres.items()},
                    "count": {k: v for k, v in cres.items()},
                    "adjusted_threshold": float(new_thr),
                }

            # Finales, kompaktes Log ohne Sets
            final_log = {"phase": PH_DETECT, "tick": int(tick)}
            for key in ("basic", "distance", "count", "multi"):
                if key in res_last and isinstance(res_last[key], dict):
                    # hart begrenzen, um ID-Prop-Overflow zu vermeiden
                    for k, v in list(res_last[key].items())[:20]:
                        # nur primitive Typen durchlassen
                        if isinstance(v, (str, int, float, bool)) or v is None:
                            final_log[f"{key}.{k}"] = v
                elif key in res_last:
                    final_log[key] = str(res_last[key])
            if "adjusted_threshold" in res_last:
                final_log["adjusted_threshold"] = float(res_last["adjusted_threshold"])
            scn[K_LAST] = final_log
            scn[K_PHASE] = PH_BIDI_S
            return {'RUNNING_MODAL'}

        # -----------------------------
        # Second-Cycle: Spike-Filter
        # -----------------------------
        if phase == PH_SPIKE:
            try:
                # aktuellen Arbeits-Threshold holen (fällt zuvor ggf. in PH_FMAX)
                try:
                    curr_thr = float(scn.get(K_ERR_THR_CURR, scn.get("error_threshold_px", 100.0)))
                except Exception:
                    curr_thr = float(scn.get("error_threshold_px", 100.0))

                # Spike-Filter ausführen – Threshold kommt *nur* vom Coordinator
                # (Helper/spike_filter_cycle.py hat keine eigene Absenklogik mehr)
                sres = run_marker_spike_filter_cycle(
                    context,
                    track_threshold=float(curr_thr),
                    # wir cleanen Segmente explizit im nächsten Step (PH_CSEG)
                    run_segment_cleanup=False,
                )
                scn[K_LAST] = {"phase": PH_SPIKE, **(sres if isinstance(sres, dict) else {}), "tick": tick}
                print(f"[Coordinator] SPIKE_FILTER(thr={curr_thr}) → {sres}")
            except Exception as ex:
                scn[K_LAST] = {"phase": PH_SPIKE, "status": "FAILED", "reason": str(ex), "tick": tick}
                print(f"[Coordinator] SPIKE_FILTER FAILED → {ex}")

            # Weiter im Second-Cycle
            scn[K_PHASE] = PH_CSEG
            return {'RUNNING_MODAL'}        
        if phase == PH_CSEG:
            # Second-Cycle: Kurzsegmente-Cleanup (nach SPIKE)
            try:
                # Default-Min-Länge: tco_min_seg_len → frames_track → 25
                scene = context.scene
                try:
                    min_len = int(scene.get("tco_min_seg_len", 0)) or int(getattr(scene, "frames_track", 0)) or 25
                except Exception:
                    min_len = 25
                cres = clean_short_segments(
                    context,
                    min_len=int(min_len),
                    treat_muted_as_gap=True,
                    verbose=False,
                )
                scn[K_LAST] = {"phase": PH_CSEG, **(cres if isinstance(cres, dict) else {}), "tick": tick}
                print(f"[Coordinator] CLEAN_SHORT_SEGMENTS(min_len={min_len}) → {cres}")
            except Exception as ex:
                scn[K_LAST] = {"phase": PH_CSEG, "status": "FAILED", "reason": str(ex), "tick": tick}
                print(f"[Coordinator] CLEAN_SHORT_SEGMENTS FAILED → {ex}")
            # Weiter zu Short-Track-Cleaner
            scn[K_PHASE] = PH_CTRK
            return {'RUNNING_MODAL'}

        if phase == PH_CTRK:
            # Second-Cycle: Kurztracks-Cleanup (nach CSEG)
            try:
                processed, affected = clean_short_tracks(context)
                scn[K_LAST] = {"phase": PH_CTRK, "status": "OK", "processed": processed, "affected": affected, "tick": tick}
                print(f"[Coordinator] CLEAN_SHORT_TRACKS → processed={processed}, affected={affected}")
            except Exception as ex:
                scn[K_LAST] = {"phase": PH_CTRK, "status": "FAILED", "reason": str(ex), "tick": tick}
                print(f"[Coordinator] CLEAN_SHORT_TRACKS FAILED → {ex}")
            scn[K_PHASE] = PH_FMAX
            return {'RUNNING_MODAL'}

        if phase == PH_FMAX:
            # Second-Cycle Step 3: Max-Marker-Frame suchen
            fmr = run_find_max_marker_frame(context, log_each_frame=False, return_observed_min=True)
            scn[K_LAST] = {"phase": PH_FMAX, **fmr, "tick": tick}
            print(f"[Coordinator] FIND_MAX_MARKER → {fmr}")
            if fmr.get("status") == "FOUND":
                # → zurück in Cycle 1 und Error-Threshold resetten
                scn[K_ERR_THR_CURR] = float(scn.get(K_ERR_THR_BASE, scn.get("error_threshold_px", 100.0)))
                # Zyklus-2-Init-Flag zurücksetzen
                scn.pop(K_CYCLE2_INIT, None)
                scn[K_PHASE] = PH_FIND
                return {'RUNNING_MODAL'}
            # Kein Frame gefunden → Threshold senken (*0.9), Floor 10 px
            try:
                curr = float(scn.get(K_ERR_THR_CURR, scn.get("error_threshold_px", 100.0)))
            except Exception:
                curr = float(scn.get("error_threshold_px", 100.0))
            next_thr = max(ERR_THR_FLOOR, curr * 0.9)

            # Wenn Floor erreicht, noch einen letzten Cycle ohne weitere Senkung
            if next_thr <= ERR_THR_FLOOR + 1e-6:
                if not scn.get("tco_floor_cycle_done", False):
                    # einmaliges Flag setzen und Cycle nochmal starten
                    scn["tco_floor_cycle_done"] = True
                    scn[K_ERR_THR_CURR] = float(ERR_THR_FLOOR)
                    print("[Coordinator] Threshold-Floor erreicht → letzter Zyklus läuft")
                    scn[K_PHASE] = PH_SPIKE
                else:
                    print("[Coordinator] Second-Cycle beendet: letzter Zyklus abgeschlossen")
                    scn[K_PHASE] = PH_FIN
            else:
                scn[K_ERR_THR_CURR] = float(next_thr)
                scn[K_LAST].update({"err_thr_curr_next": float(next_thr)})
                scn[K_PHASE] = PH_SPIKE
            return {'RUNNING_MODAL'}
            # (ENTFERNT) Der DETECT-Loop war hier fälschlich hinter PH_FMAX platziert und somit unerreichbar.

        if phase == PH_BIDI_S:
            # Falls Bidi bereits aktiv ist, direkt in die Wait-Phase
            if scn.get(K_BIDI_ACTIVE, False):
                scn[K_PHASE] = PH_BIDI_W
                return {'RUNNING_MODAL'}
            try:
                # Start: Bidirectional Track Operator IM CLIP_EDITOR-Kontext auslösen
                wm = bpy.context.window_manager
                win = None; area = None; region = None; space = None
                if wm:
                    for w in wm.windows:
                        scr = getattr(w, "screen", None)
                        if not scr: continue
                        for a in scr.areas:
                            if a.type == 'CLIP_EDITOR':
                                r = next((r for r in a.regions if r.type == 'WINDOW'), None)
                                if r:
                                    win, area, region = w, a, r
                                    space = a.spaces.active if hasattr(a, "spaces") else None
                                    break
                        if win: break
                if win and area and region and space:
                    override = {"window": win, "area": area, "region": region, "space_data": space, "scene": scn}
                    with bpy.context.temp_override(**override):
                        bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                else:
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
            # Ergebnis zurücksetzen, um stale states zu vermeiden
            try:
                scn.pop(K_BIDI_RESULT, None)
            except Exception:
                pass
            
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
            # Sicherheit: Flag zurücksetzen
            try:
                context.scene.pop(K_CYCLE2_INIT, None)
            except Exception:
                pass
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
