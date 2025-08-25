from __future__ import annotations
"""
Tracking-Orchestrator (STRICT)
------------------------------
Strikter FSM-Ablauf: FIND_LOW → JUMP → DETECT → BIDI (modal) → CLEAN_SHORT → Loop.

Solve-Workflow (dieser Build):
- Solve wird asynchron per Helper/solve_camera.solve_watch_clean() gestartet.
- Nach *jedem* erfolgreichen Solve → IMMER zuerst REFINE (modal, UI sichtbar).
- Nach abgeschlossenem Refine → Solve-Retry → zurück zu SOLVE_WAIT.
- Erst danach Error-Bewertung:
    - Error weiterhin > threshold → zurück zu FIND_LOW (ohne Lösch-Operationen)
    - Error ≤ threshold → FINALIZE
"""

import os
from typing import Optional, Dict

import bpy
from ..Helper.triplet_grouping import run_triplet_grouping  # top-level import
from ..Helper.refine_high_error import run_refine_on_high_error

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

# Solve-Wait: Anzahl der Timer-Ticks (Timer steht auf 0.25 s in invoke())
_SOLVE_WAIT_TICKS_DEFAULT = 48  # ≈ 12 s
_SOLVE_WAIT_TRIES_PER_TICK = 1  # pro Tick nur ein kurzer Versuch (nicht blockierend)


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


# ---------------------------------------------------------------------------
# Solve-Error Utilities
# ---------------------------------------------------------------------------

def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _compute_solve_error(context) -> Optional[float]:
    clip = _get_active_clip(context)
    if not clip:
        return None
    try:
        recon = clip.tracking.objects.active.reconstruction
    except Exception:
        return None
    if not getattr(recon, "is_valid", False):
        return None

    if hasattr(recon, "average_error"):
        try:
            return float(recon.average_error)
        except Exception:
            pass

    try:
        errs = [float(c.average_error) for c in getattr(recon, "cameras", [])]
        if not errs:
            return None
        return sum(errs) / len(errs)
    except Exception:
        return None


def _wait_for_reconstruction(context, tries: int = 12) -> bool:
    clip = _get_active_clip(context)
    if not clip:
        return False
    for _ in range(max(1, int(tries))):
        try:
            recon = clip.tracking.objects.active.reconstruction
            if getattr(recon, "is_valid", False):
                return True
        except Exception:
            pass
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
    return False


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (STRICT)"
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
    _solve_wait_ticks: int = 0

    # Refine-Modalsteuerung
    _waiting_refine: bool = False
    _post_solve_refine_done: bool = False

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
        _safe_report(self, {"INFO"}, "Coordinator (STRICT) gestartet")
        print("[Coord] START (STRICT Detect→Bidi→CleanShort)")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if context.scene.get(_LOCK_KEY, False):
            return {"RUNNING_MODAL"}

        # --- Wartephase auf Refine-Modaloperator ----------------------------
        if self._waiting_refine:
            scn = context.scene
            if (scn.get("refine_active") is False) and bool(scn.get("refine_result", "")):
                result = scn.get("refine_result", "CANCELLED")
                self._waiting_refine = False

                if result != "FINISHED":
                    msg = scn.get("refine_error_msg", "")
                    if msg:
                        _safe_report(self, {'WARNING'}, f"Refine aborted ({result}): {msg}")
                    else:
                        _safe_report(self, {'WARNING'}, f"Refine aborted ({result})")
                    # Nach Abbruch → zurück zu FIND_LOW (kein Cleanup)
                    self._post_solve_refine_done = True
                    self._state = "FIND_LOW"
                    return {"RUNNING_MODAL"}

                # Refine erfolgreich → Solve-Retry starten
                try:
                    from ..Helper.solve_camera import solve_watch_clean  # type: ignore
                    print("[Coord] REFINE done → retry solve_watch_clean()")
                    solve_watch_clean(context)
                except Exception as ex2:
                    print(f"[Coord] SOLVE retry failed: {ex2!r}")

                self._solve_wait_ticks = int(getattr(context.scene, "solve_wait_ticks", _SOLVE_WAIT_TICKS_DEFAULT))
                self._post_solve_refine_done = True
                self._state = "SOLVE_WAIT"
                return {"RUNNING_MODAL"}

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
        self._solve_wait_ticks = 0
        self._waiting_refine = False
        self._post_solve_refine_done = False

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
            # Sofortiger Abbruch ohne weitere Schritte
            print("[Coord] FIND_LOW → NONE → keine Frames mehr → FINALIZE")
            self._state = "FINALIZE"

        else:
            context.scene[_GOTO_KEY] = context.scene.frame_current
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FAILED ({result.get('reason', '?')}) → JUMP (best-effort)")
            self._state = "JUMP"

        return {"RUNNING_MODAL"}

    def _state_solve(self, context):
        """Solve-Start (asynchron) → dann SOLVE_WAIT (mit Post-Solve-Refine)."""
        try:
            from ..Helper.solve_camera import solve_watch_clean  # type: ignore
            print("[Coord] SOLVE → solve_watch_clean()")
            res = solve_watch_clean(context)
            print(f"[Coord] SOLVE → solve_watch_clean() returned {res}")
        except Exception as ex:
            print(f"[Coord] SOLVE failed to start: {ex!r}")
            return self._handle_failed_solve(context)

        self._solve_wait_ticks = int(_SOLVE_WAIT_TICKS_DEFAULT)
        self._post_solve_refine_done = False   # pro Solve-Phase genau 1x Refine
        self._state = "SOLVE_WAIT"
        return {"RUNNING_MODAL"}

    def _state_solve_wait(self, context):
        """Nicht-blockierendes Warten → nach erstem Solve IMMER Refine; danach Bewertung."""
        if not _wait_for_reconstruction(context, tries=_SOLVE_WAIT_TRIES_PER_TICK):
            self._solve_wait_ticks -= 1
            print(f"[Coord] SOLVE_WAIT → waiting ({self._solve_wait_ticks} ticks left)")
            if self._solve_wait_ticks > 0:
                return {"RUNNING_MODAL"}
            print("[Coord] SOLVE_WAIT → timeout → FAIL-SOLVE fallback")
            return self._handle_failed_solve(context)

        # Rekonstruktion ist gültig → Schritt 1: REFINE (wenn noch nicht getan)
        if not self._post_solve_refine_done:
            th = float(getattr(context.scene, "error_track", 2.0) or 2.0) * 10.0
            print("[Coord] SOLVE_WAIT → launch REFINE (always-first after solve)")
            self._launch_refine(context, threshold=th)
            return {"RUNNING_MODAL"}

        # Schritt 2: Error-Bewertung NACH dem Refine + Solve-Retry
        threshold = float(getattr(context.scene, "error_track", 2.0) or 2.0)
        current_err = _compute_solve_error(context)
        print(f"[Coord] SOLVE_WAIT(after refine) → error={current_err!r} vs. threshold={threshold}")

        if current_err is None or current_err > threshold:
            print("[Coord] SOLVE_WAIT → error high/None → FIND_LOW")
            self._state = "FIND_LOW"
            return {"RUNNING_MODAL"}

        print("[Coord] SOLVE_WAIT → FINALIZE")
        self._state = "FINALIZE"
        return {"RUNNING_MODAL"}

    # ---------------- Refine-Launch ----------------

    def _launch_refine(self, context, *, threshold: float) -> None:
        scn = context.scene
        if scn.get(_BIDI_ACTIVE_KEY, False) or scn.get("solve_active") or scn.get("refine_active"):
            _safe_report(self, {'WARNING'}, "Busy: tracking/solve/refine active")
            return

        res = run_refine_on_high_error(context, threshold=threshold)
        if res.get("status") == "STARTED":
            self._waiting_refine = True
        else:
            self._waiting_refine = False
            self._post_solve_refine_done = True

    # ---------------- Fehlerpfad ----------------

    def _handle_failed_solve(self, context):
        """Wenn Solve keine gültige Reconstruction liefert:
        → erst Refine (modal), danach zurück zu FIND_LOW (kein Cleanup).
        """
        print("[Coord] FAIL-SOLVE → starte REFINE (modal), danach FIND_LOW")
        th = float(getattr(context.scene, "error_track", 2.0) or 2.0) * 10.0

        res = run_refine_on_high_error(context, threshold=th)
        if res.get("status") == "STARTED":
            self._waiting_refine = True
            return {"RUNNING_MODAL"}

        print("[Coord] FAIL-SOLVE → no frames to refine → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

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
        # No-Op: Bestandteil der FSM, aber ohne Operationen
        print("[Coord] CLEAN_SHORT (no-op) → FIND_LOW")
        self._state = "FIND_LOW"
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
    # Minimaler Sanity-Check
    print("[SelfTest] basic import OK")
