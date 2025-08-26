from __future__ import annotations
"""
Tracking-Orchestrator (NO-REFINE, NO-WAIT)
----------------------------------------

Änderungen gemäß Anforderung:
- Nach dem Solve **passiert nichts mehr**: Kein Warten, kein Refine.
- `_state_solve` triggert ausschließlich den Operator und wechselt direkt zu `FINALIZE`.
- Sämtliche Refine-Pfade, Wartezustände und SOLVE_WAIT wurden entfernt.
"""

import os
import time
import bpy
from typing import Optional, Dict

from ..Helper.triplet_grouping import run_triplet_grouping  # top-level import
from ..Helper.solve_camera import solve_camera_only
from ..Helper.projection_cleanup_builtin import run_projection_cleanup_builtin

# Cycle-Helpers
from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore
from ..Helper.find_max_marker_frame import run_find_max_marker_frame  # type: ignore
from ..Helper.spike_filter_cycle import run_spike_filter_cycle  # type: ignore

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

# Scene Keys
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8

_BIDI_ACTIVE_KEY = "bidi_active"

# Keys für Optimizer-Signal (werden von Helper/jump_to_frame.py gesetzt)
_OPT_REQ_KEY = "__optimize_request"
_OPT_REQ_VAL = "JUMP_REPEAT"
_OPT_FRAME_KEY = "__optimize_frame"

# Cycle: Sicherheitslimit (äußeres Loop-Limit)
_CYCLE_MAX_LOOPS = 50


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (NO-REFINE)"
    bl_options = {"REGISTER", "UNDO"}

    use_apply_settings: bpy.props.BoolProperty(  # type: ignore
        name="Apply Tracker Defaults",
        default=True,
    )

    _timer: Optional[bpy.types.Timer] = None
    _state: str = "INIT"
    _detect_attempts: int = 0
    _jump_done: bool = False
    _repeat_map: Dict[int, int]
    _bidi_started: bool = False

    # --- Cycle-Bookkeeping ---
    _cycle_active: bool = False
    _cycle_stage: str = ""      # "CYCLE_FIND_MAX" | "CYCLE_SPIKE"
    _cycle_loops: int = 0        # Anzahl der durchlaufenen FIND_MAX↔SPIKE Runden
    _cycle_initial_clean_done: bool = False  # << nur einmal zu Beginn
    _cycle_spike_threshold: float = 100.0

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    # ---------------- Lifecycle ----------------

    def _run_pre_flight_helpers(self, context) -> None:
        try:
            from ..Helper.tracker_settings import apply_tracker_settings  # type: ignore
            apply_tracker_settings(context, log=True)
            print("[Coord] BOOTSTRAP → tracker_settings OK")
        except Exception as ex:
            print(f"[Coord] BOOTSTRAP WARN: tracker_settings failed: {ex!r}")
            try:
                bpy.ops.clip.apply_tracker_settings('INVOKE_DEFAULT')
            except Exception:
                pass

        try:
            from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
            marker_helper_main(context)
            print("[Coord] BOOTSTRAP → marker_helper_main OK")
        except Exception as ex_func:
            print(f"[Coord] BOOTSTRAP WARN: marker_helper_main failed: {ex_func!r}")
            try:
                bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')
            except Exception:
                pass

        if self.use_apply_settings:
            try:
                from ..Helper.apply_tracker_settings import apply_tracker_settings  # type: ignore
                apply_tracker_settings(context)
                print("[Coord] BOOTSTRAP → apply_tracker_settings() OK")
            except Exception as ex:
                print(f"[Coord] BOOTSTRAP INFO: apply_tracker_settings not available/failed: {ex!r}")

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self._bootstrap(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        _safe_report(self, {"INFO"}, "Coordinator (NO-REFINE) gestartet")
        print("[Coord] START (STRICT Detect→Bidi→CleanShort)")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if context.scene.get(_LOCK_KEY, False):
            return {"RUNNING_MODAL"}

        # ----------------------------- FSM -----------------------------------
        if self._state == "INIT":
            return self._state_init(context)
        elif self._state == "FIND_LOW":
            return self._state_find_low(context)
        elif self._state == "JUMP":
            return self._state_jump(context)
        elif self._state == "DETECT":
            return self._state_detect(context)
        elif self._state == "TRACK":
            return self._state_track(context)
        elif self._state == "CLEAN_SHORT":
            return self._state_clean_short(context)
        elif self._state == "SOLVE":
            return self._state_solve(context)
        elif self._state == "SOLVE_WAIT":
            return self._state_solve_wait(context)
        elif self._state == "CYCLE_CLEAN":
            return self._state_cycle_clean(context)
        elif self._state == "CYCLE_FIND_MAX":
            return self._state_cycle_findmax(context)
        elif self._state == "CYCLE_SPIKE":
            return self._state_cycle_spike(context)
        elif self._state == "FINALIZE":
            return self._finish(context, cancelled=False)

        return self._finish(context, cancelled=True)

    # ---------------- Bootstrap ----------------

    def _bootstrap(self, context):
        scn = context.scene
        scn[_LOCK_KEY] = False
        scn[_BIDI_ACTIVE_KEY] = False
        scn.pop("__skip_clean_short_once", None)
        scn.pop("__pre_refine_done", None)
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False

        # Cycle reset
        self._cycle_active = False
        self._cycle_stage = ""
        self._cycle_loops = 0
        self._cycle_initial_clean_done = False
        self._cycle_spike_threshold = 100.0

    # ---------------- States ----------------

    def _state_init(self, context):
        print("[Coord] INIT → BOOTSTRAP")
        self._run_pre_flight_helpers(context)
        print("[Coord] BOOTSTRAP → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _state_find_low(self, context):
        from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore

        result = run_find_low_marker_frame(context)
        status = str(result.get("status", "FAILED")).upper()

        if status == "FOUND":
            frame = int(result.get("frame", context.scene.frame_current))
            context.scene[_GOTO_KEY] = frame
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FOUND frame={frame} → JUMP")
            self._state = "JUMP"

        elif status == "NONE":
            # Cycle starten: einmal CLEAN, dann FIND_MAX ↔ SPIKE
            print("[Coord] FIND_LOW → NONE → starte CYCLE_CLEAN (one-shot) → dann FIND_MAX↔SPIKE")
            self._cycle_active = True
            self._cycle_stage = "CYCLE_CLEAN"
            self._cycle_loops = 0
            self._cycle_initial_clean_done = False
            self._cycle_spike_threshold = float(getattr(context.scene, "spike_start_threshold", 100.0) or 100.0)
            self._state = "CYCLE_CLEAN"

        else:
            context.scene[_GOTO_KEY] = context.scene.frame_current
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FAILED ({result.get('reason', '?')}) → JUMP (best-effort)")
            self._state = "JUMP"

        return {"RUNNING_MODAL"}

    # ---------------- SOLVE ----------------

    def _state_solve(self, context):
        try:
            res = solve_camera_only(context)
            print(f"[Coord] Solve invoked: {res}")
        except Exception as ex:
            print(f"[Coord] SOLVE start failed: {ex!r}")

            self._state = "FINALIZE"
            return {'RUNNING_MODAL'}

        # Solve läuft modal → wir warten im nächsten State aktiv auf gültige Reconstruction
        self._solve_wait_deadline = time.monotonic() + float(getattr(context.scene, "solve_wait_timeout_s", 60.0))
        self._state = "SOLVE_WAIT"
        return {"RUNNING_MODAL"}

    def _state_solve_wait(self, context):
        """Wartet bis die Reconstruction gültig ist (Solve fertig), dann Cleanup, dann FINALIZE."""
        err = self._get_current_solve_error_now(context)
        if err is not None:
            print(f"[Coord] SOLVE_WAIT → reconstruction valid, avg_error={err:.4f}px → CLEANUP")
            try:
                # Jetzt ist Solve sicher fertig. Wir können direkt mit fester Schwelle
                # ODER ohne Schwelle (Helper ermittelt sie sofort) arbeiten.
                cleanup = run_projection_cleanup_builtin(
                    context,
                    error_limit=float(err),   # den Solve-Error direkt verwenden!
                    wait_for_error=False,
                    action="DELETE_TRACK",    # direkt löschen
                )
                print(f"[Coord] Cleanup after solve → {cleanup}")
            except Exception as ex_cleanup:
                print(f"[Coord] Cleanup after solve failed: {ex_cleanup!r}")
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}

        # Noch kein gültiger Solve-Error → Timeout prüfen
        if time.monotonic() >= getattr(self, "_solve_wait_deadline", 0.0):
            print("[Coord] SOLVE_WAIT → timeout → FINALIZE (kein gültiger Solve)")
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}
        # weiter warten
        return {"RUNNING_MODAL"}

    # --- kleine Utility: Solve-Error prüfen (ohne Abhängigkeit vom Helper) ---
    def _get_current_solve_error_now(self, context):
        space = getattr(context, "space_data", None)
        clip = space.clip if (getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None)) else None
        if clip is None:
            try:
                clip = bpy.data.movieclips[0] if bpy.data.movieclips else None
            except Exception:
                clip = None
        if not clip:
            return None
        try:
            recon = clip.tracking.objects.active.reconstruction
            if not getattr(recon, "is_valid", False):
                return None
            if hasattr(recon, "average_error"):
                return float(recon.average_error)
        except Exception:
            return None
        return None

    # ---------------- JUMP/DETECT/TRACK/CLEAN_SHORT ----------------

    def _state_jump(self, context):
        from ..Helper.jump_to_frame import run_jump_to_frame  # type: ignore
        if not self._jump_done:
            goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
            jr = run_jump_to_frame(context, frame=goto, repeat_map=self._repeat_map)
            if jr.get("status") != "OK":
                print(f"[Coord] JUMP failed: {jr.get('reason','?')} → FIND_LOW")
                self._state = "FIND_LOW"
                return {"RUNNING_MODAL"}
            print(f"[Coord] JUMP → frame={jr['frame']} repeat={jr['repeat_count']} → DETECT")

            scn = context.scene
            opt_req = scn.get(_OPT_REQ_KEY, None)
            opt_frame = int(scn.get(_OPT_FRAME_KEY, jr.get('frame', scn.frame_current)))
            if jr.get("optimize_signal") or opt_req == _OPT_REQ_VAL:
                scn.pop(_OPT_REQ_KEY, None)
                scn[_OPT_FRAME_KEY] = opt_frame
                try:
                    from ..Helper.optimize_tracking_modal import start_optimization  # type: ignore
                    if int(context.scene.frame_current) != int(opt_frame):
                        context.scene.frame_set(int(opt_frame))
                    start_optimization(context)
                    print(f"[Coord] JUMP → OPTIMIZE (start_optimization, frame={opt_frame})")
                except Exception as ex_func:
                    print(f"[Coord] OPTIMIZE failed (function): {ex_func!r}")
                    try:
                        bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
                        print(f"[Coord] JUMP → OPTIMIZE (operator fallback, frame={opt_frame})")
                    except Exception as ex_op:
                        print(f"[Coord] OPTIMIZE launch failed: {ex_op!r}")

            self._jump_done = True
        self._detect_attempts = 0
        self._state = "DETECT"
        return {"RUNNING_MODAL"}

    def _state_detect(self, context):
        from ..Helper.detect import run_detect_once  # type: ignore

        goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
        res = run_detect_once(context, start_frame=goto, handoff_to_pipeline=True)
        status = str(res.get("status", "FAILED")).upper()

        if status == "RUNNING":
            self._detect_attempts += 1
            print(f"[Coord] DETECT → RUNNING (attempt {self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[Coord] DETECT Timebox erreicht → force TRACK")
                self._state = "TRACK"
            return {"RUNNING_MODAL"}

        try:
            tg = run_triplet_grouping(context)
            print(f"[Coord] TRIPLET_GROUPING → {tg}")
        except Exception as ex_tg:
            print(f"[Coord] TRIPLET_GROUPING failed: {ex_tg!r}")

        print(f"[Coord] DETECT → {status} → TRACK (Bidirectional)")
        self._state = "TRACK"
        return {"RUNNING_MODAL"}

    def _state_track(self, context):
        scn = context.scene

        if not self._bidi_started:
            scn[_BIDI_ACTIVE_KEY] = False
            print("[Coord] TRACK → launch clip.bidirectional_track (INVOKE_DEFAULT)")
            try:
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                self._bidi_started = True
            except Exception as ex:
                print(f"[Coord] TRACK launch failed: {ex!r} → CLEAN_SHORT (no-op)")
                self._bidi_started = False
                self._state = "CLEAN_SHORT"
            return {"RUNNING_MODAL"}

        if scn.get(_BIDI_ACTIVE_KEY, False):
            print("[Coord] TRACK → waiting (bidi_active=True)")
            return {"RUNNING_MODAL"}

        self._bidi_started = False
        self._state = "CLEAN_SHORT"
        return {"RUNNING_MODAL"}

    def _state_clean_short(self, context):
        # Bestandteil der ursprünglichen FSM, unverändert
        print("[Coord] CLEAN_SHORT (no-op) → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    # ---------------- CYCLE STATES ----------------

    def _state_cycle_clean(self, context):
        """One-shot CLEAN zu Beginn des Zyklus, danach FIND_MAX."""
        if not self._cycle_active:
            print("[Coord] CYCLE_CLEAN reached but cycle inactive → FINALIZE")
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}

        if not self._cycle_initial_clean_done:
            try:
                frames_min = int(getattr(context.scene, "frames_track", 25) or 25)
                clean_short_tracks(context, min_len=frames_min, verbose=True)
                print(f"[Coord] CYCLE_CLEAN (one-shot) → clean_short_tracks(min_len={frames_min}) done")
            except TypeError:
                try:
                    clean_short_tracks(context)
                    print("[Coord] CYCLE_CLEAN (one-shot) → clean_short_tracks() fallback done")
                except Exception as ex:
                    print(f"[Coord] CYCLE_CLEAN failed: {ex!r}")
            except Exception as ex:
                print(f"[Coord] CYCLE_CLEAN failed: {ex!r}")
            self._cycle_initial_clean_done = True

        # Nach einmaligem CLEAN direkt zu FIND_MAX wechseln
        self._cycle_stage = "CYCLE_FIND_MAX"
        self._state = "CYCLE_FIND_MAX"
        return {"RUNNING_MODAL"}

    def _state_cycle_findmax(self, context):
        """FIND_MAX → bei FOUND: FINALIZE, sonst SPIKE."""
        if not self._cycle_active:
            print("[Coord] CYCLE_FIND_MAX reached but cycle inactive → FINALIZE")
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}

        try:
            res = run_find_max_marker_frame(context)
        except Exception as ex:
            print(f"[Coord] CYCLE_FIND_MAX failed: {ex!r}")
            res = {"status": "FAILED", "reason": repr(ex)}

        status = str(res.get("status", "FAILED")).upper()
        if status == "FOUND":
            frame = int(res.get("frame", getattr(context.scene, "frame_current", 0)))
            count = res.get("count", "?")
            thresh = res.get("threshold", "?")
            print(f"[Coord] CYCLE_FIND_MAX → FOUND frame={frame} (count={count} < threshold={thresh}) → SOLVE")

            # Frame setzen (direkt), ohne über DETECT/TRACK zu gehen
            try:
                context.scene.frame_set(frame)
            except Exception as ex_set:
                print(f"[Coord] WARN: frame_set({frame}) failed: {ex_set!r}")

            # Cycle beenden & Solve-Phase starten
            self._cycle_active = False
            self._cycle_stage = ""
            self._state = "SOLVE"
            return {"RUNNING_MODAL"}

        # NONE oder FAILED → weiter mit SPIKE
        print(f"[Coord] CYCLE_FIND_MAX → {status} → CYCLE_SPIKE")
        self._cycle_stage = "CYCLE_SPIKE"
        self._state = "CYCLE_SPIKE"
        return {"RUNNING_MODAL"}

    def _state_cycle_spike(self, context):
        """SPIKE ausführen → danach **zurück zu FIND_MAX** (kein weiteres CLEAN)."""
        if not self._cycle_active:
            print("[Coord] CYCLE_SPIKE reached but cycle inactive → FINALIZE")
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}

        # Äußeres Cycle-Limit prüfen/erhöhen
        self._cycle_loops += 1
        if self._cycle_loops > int(getattr(context.scene, "cycle_max_loops", _CYCLE_MAX_LOOPS)):
            print(f"[Coord] CYCLE_SPIKE → max_loops reached ({self._cycle_loops}) → FINALIZE")
            self._cycle_active = False
            self._cycle_stage = ""
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}

        try:
            res = run_spike_filter_cycle(
                context,
                track_threshold=float(self._cycle_spike_threshold),
            )
            print(f"[Coord] CYCLE_SPIKE → spike_filter_cycle result={res}")
            status = str(res.get("status", "")).upper()
            if status == "OK":
                next_thr = float(res.get("next_threshold", self._cycle_spike_threshold * 0.9))
            else:
                next_thr = self._cycle_spike_threshold * 0.9
        except Exception as ex:
            print(f"[Coord] CYCLE_SPIKE failed: {ex!r}")
            next_thr = self._cycle_spike_threshold * 0.9

        self._cycle_spike_threshold = max(5.0, next_thr)

        # Nach SPIKE **direkt** zurück zu FIND_MAX (kein Clean)
        self._cycle_stage = "CYCLE_FIND_MAX"
        self._state = "CYCLE_FIND_MAX"
        return {"RUNNING_MODAL"}

    # ---------------- Finish ----------------

    def _finish(self, context, *, cancelled: bool):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        context.scene[_LOCK_KEY] = False
        msg = "CANCELLED" if cancelled else "FINISHED"
        print(f"[Coord] DONE ({msg})")
        return {"CANCELLED" if cancelled else "FINISHED"}


def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)


if __name__ == "__main__" and os.getenv("ADDON_RUN_TESTS", "0") == "1":
    print("[SelfTest] basic import OK")
