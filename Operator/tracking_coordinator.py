from __future__ import annotations

import os
import time
import bpy
from bpy.types import Scene
from bpy.props import BoolProperty, FloatProperty
from typing import Optional, Dict, Any, Callable, Tuple

from ..Helper.triplet_grouping import run_triplet_grouping  # top-level import
from ..Helper.solve_camera import solve_camera_only
from ..Helper.refine_high_error import start_refine_modal
from ..Helper.projection_cleanup_builtin import run_projection_cleanup_builtin

# Cycle-Helpers
from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore
from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
from ..Helper.spike_filter_cycle import run_spike_filter_cycle  # type: ignore
from ..Helper.find_max_marker_frame import run_find_max_marker_frame  # optional, aktuell ungenutzt

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

# Scene Keys
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8

_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"

# Keys für Optimizer-Signal (werden von Helper/jump_to_frame.py gesetzt)
_OPT_REQ_KEY = "__optimize_request"
_OPT_REQ_VAL = "JUMP_REPEAT"
_OPT_FRAME_KEY = "__optimize_frame"

# Defaults
_DEFAULT_SOLVE_WAIT_S = 60.0
_DEFAULT_SPIKE_START = 100.0
_DEFAULT_REFINE_TIMEOUT_S = 30.0


def _tco_log(msg: str) -> None:
    print(f"[tracking_coordinator] {msg}")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_call(func: Callable[..., Any], *args, **kwargs) -> Tuple[bool, Any]:
    try:
        return True, func(*args, **kwargs)
    except Exception as ex:  # noqa: BLE001
        _tco_log(f"_safe_call({getattr(func, '__name__', 'func')}): {ex!r}")
        return False, ex


def _safe_ops_invoke(ops_path: str, *args, **kwargs) -> Tuple[bool, Any]:
    try:
        mod, name = ops_path.split(".", 1)
        op = getattr(getattr(bpy.ops, mod), name)
    except Exception as ex:  # noqa: BLE001
        _tco_log(f"_safe_ops_invoke: resolve failed for '{ops_path}': {ex!r}")
        return False, ex
    try:
        return True, op(*args, **kwargs)
    except Exception as ex:  # noqa: BLE001
        _tco_log(f"_safe_ops_invoke: call failed for '{ops_path}': {ex!r}")
        return False, ex


def _scene_float(scene: bpy.types.Scene, key: str, default: float) -> float:
    try:
        v = getattr(scene, key, default)
        v = default if v is None else v
        return float(v)
    except Exception:
        return float(default)


def _have_clip(context: bpy.types.Context) -> bool:
    space = getattr(context, "space_data", None)
    return bool(getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None))


def _current_solve_error(context: bpy.types.Context) -> Optional[float]:
    """Average-Error aus aktiver Reconstruction (oder None)."""
    space = getattr(context, "space_data", None)
    clip = space.clip if (getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None)) else None
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


def _wait_for_valid_reconstruction(
    context: bpy.types.Context, *, timeout_s: float, poll_s: float = 0.05
) -> Optional[float]:
    """Pollt bis valide Reconstruction oder Timeout; liefert avg_error oder None."""
    deadline = time.monotonic() + float(timeout_s)
    while time.monotonic() < deadline:
        err = _current_solve_error(context)
        if err is not None:
            return float(err)
        try:
            time.sleep(float(poll_s))
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Optionales Spike-Value-Memo (nur Hilfsfeature)
# ---------------------------------------------------------------------------

def register_scene_state() -> None:
    if not hasattr(Scene, "tco_spike_value"):
        Scene.tco_spike_value = FloatProperty(
            name="Spike Filter Value",
            description="Finaler Wert für spike_filter_cycle, der einmalig ausgelöst werden kann.",
            default=0.0,
        )
    if not hasattr(Scene, "tco_spike_pending"):
        Scene.tco_spike_pending = BoolProperty(
            name="Spike Pending",
            description="True, wenn ein finaler Spike-Wert gemerkt wurde und auf Cleanup wartet.",
            default=False,
        )


def unregister_scene_state() -> None:
    for attr in ("tco_spike_value", "tco_spike_pending"):
        if hasattr(Scene, attr):
            delattr(Scene, attr)


def remember_spike_filter_value(value: float, *, context: bpy.types.Context | None = None) -> None:
    ctx = context or bpy.context
    scene = ctx.scene
    scene.tco_spike_value = float(value)
    scene.tco_spike_pending = True
    _tco_log(f"remember_spike_filter_value: value={scene.tco_spike_value:.6f}, pending=True")


def trigger_spike_filter_once(value: float, *, context: bpy.types.Context | None = None) -> None:
    ctx = context or bpy.context
    scene = ctx.scene
    scene["tco_spike_suppress_remember"] = True
    try:
        try:
            from ..Helper import spike_filter_cycle as _sfc  # lazy import
            if hasattr(_sfc, "run_with_value"):
                _sfc.run_with_value(ctx, float(value))
                return
        except Exception as ex:  # noqa: BLE001
            _tco_log(f"direct call failed: {ex!r}; fallback to bpy.ops")
        try:
            bpy.ops.helper.spike_filter_cycle("INVOKE_DEFAULT", value=float(value))
        except Exception as ex:  # noqa: BLE001
            _tco_log(f"bpy.ops fallback failed: {ex!r}")
    finally:
        scene["tco_spike_suppress_remember"] = False


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """
    Zielablauf:

    Tracking-Loop:
      1) FIND_LOW: Solange niedrige Marker-Frames gefunden werden:
            → JUMP → DETECT → (Triplet) → TRACK (bidi) → CLEAN_SHORT → zurück zu FIND_LOW
      2) FIND_LOW liefert NONE:
            → SPIKE_FILTER_CYCLE (einmal)
            → SOLVE
            → if error ≤ error_track: FINALIZE
            → else REFINE (modal, blocking) → SOLVE → if error ≤ error_track: FINALIZE
            → else PROJECTION_CLEANUP → zurück zu FIND_LOW
    """
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator"
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

    # Solve / Evaluate book-keeping
    _pending_eval_after_solve: bool = False  # true → nach Solve steht EVAL an
    _did_refine_this_cycle: bool = False     # true → letzter Solve kam direkt nach Refine

    # Spike control
    _spike_run_done: bool = False
    _spike_threshold: float = _DEFAULT_SPIKE_START

    # Refine wait
    _refine_deadline: Optional[float] = None

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    # ---------------- Lifecycle ----------------

    def _run_pre_flight_helpers(self, context) -> None:
        # tracker_settings (defensiv)
        try:
            from ..Helper.tracker_settings import apply_tracker_settings  # type: ignore
            ok, res = _safe_call(apply_tracker_settings, context, log=True)
            if ok:
                print("[Coord] BOOTSTRAP → tracker_settings OK")
            else:
                print(f"[Coord] BOOTSTRAP WARN: tracker_settings failed: {res!r}")
                _safe_ops_invoke("clip.apply_tracker_settings", 'INVOKE_DEFAULT')
        except Exception as ex:
            print(f"[Coord] BOOTSTRAP WARN: tracker_settings import failed: {ex!r}")
            _safe_ops_invoke("clip.apply_tracker_settings", 'INVOKE_DEFAULT')

        # marker_helper_main (defensiv)
        try:
            from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
            ok, res = _safe_call(marker_helper_main, context)
            if ok:
                print("[Coord] BOOTSTRAP → marker_helper_main OK")
            else:
                print(f"[Coord] BOOTSTRAP WARN: marker_helper_main failed: {res!r}")
        except Exception as ex_func:  # noqa: BLE001
            print(f"[Coord] BOOTSTRAP WARN: marker_helper_main import failed: {ex_func!r}")
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
        print("[Coord] START (Detect→Bidi→CleanShort Loop; Spike→Solve→Eval→Refine→Wait→Solve→Eval→Cleanup)")
        return {"RUNNING_MODAL"}

    # ---------------- Bootstrap ----------------

    def _bootstrap(self, context):
        scn = context.scene
        scn[_LOCK_KEY] = False
        scn[_BIDI_ACTIVE_KEY] = False
        scn[_BIDI_RESULT_KEY] = ""
        scn.pop(_GOTO_KEY, None)

        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False

        self._pending_eval_after_solve = False
        self._did_refine_this_cycle = False
        self._spike_run_done = False
        self._spike_threshold = float(getattr(context.scene, "spike_start_threshold", _DEFAULT_SPIKE_START) or _DEFAULT_SPIKE_START)
        self._refine_deadline = None

    # ---------------- States ----------------

    def _state_init(self, context):
        print("[Coord] INIT → BOOTSTRAP")
        self._run_pre_flight_helpers(context)
        print("[Coord] BOOTSTRAP → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _state_find_low(self, context):
        if not _have_clip(context):
            print("[Coord] FIND_LOW → no active clip → retry")
            return {"RUNNING_MODAL"}

        ok, result = _safe_call(run_find_low_marker_frame, context)
        if not ok or not isinstance(result, dict):
            print(f"[Coord] FIND_LOW → FAILED (exception/invalid) → treat as NONE")
            result = {"status": "NONE", "reason": "exception-or-invalid-result"}

        status = str(result.get("status", "NONE")).upper()
        if status == "FOUND":
            frame = int(result.get("frame", context.scene.frame_current))
            context.scene[_GOTO_KEY] = frame
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FOUND frame={frame} → JUMP")
            self._state = "JUMP"
        else:
            # NONE → gewünschte Pipeline starten
            self._spike_run_done = False
            self._did_refine_this_cycle = False
            print("[Coord] FIND_LOW → NONE → SPIKE")
            self._state = "SPIKE"
        return {"RUNNING_MODAL"}

    # ---------------- JUMP/DETECT/TRACK/CLEAN_SHORT ----------------

    def _state_jump(self, context):
        from ..Helper.jump_to_frame import run_jump_to_frame  # type: ignore
        if not self._jump_done:
            goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
            ok, jr = _safe_call(run_jump_to_frame, context, frame=goto, repeat_map=self._repeat_map)
            if not ok or not isinstance(jr, dict) or jr.get("status") != "OK":
                print(f"[Coord] JUMP failed → FIND_LOW")
                self._state = "FIND_LOW"
                return {"RUNNING_MODAL"}

            print(f"[Coord] JUMP → frame={jr['frame']} repeat={jr.get('repeat_count', 0)} → DETECT")

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
                    ok_opt, res_opt = _safe_call(start_optimization, context)
                    if ok_opt:
                        print(f"[Coord] JUMP → OPTIMIZE (function, frame={opt_frame})")
                    else:
                        print(f"[Coord] OPTIMIZE failed (function): {res_opt!r}")
                        ok_op, _ = _safe_ops_invoke("clip.optimize_tracking_modal", 'INVOKE_DEFAULT')
                        if ok_op:
                            print(f"[Coord] JUMP → OPTIMIZE (operator, frame={opt_frame})")
                except Exception as ex_func:
                    print(f"[Coord] OPTIMIZE failed: {ex_func!r}")

            self._jump_done = True

        self._detect_attempts = 0
        self._state = "DETECT"
        return {"RUNNING_MODAL"}

    def _state_detect(self, context):
        from ..Helper.detect import run_detect_once  # type: ignore
        goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
        ok, res = _safe_call(run_detect_once, context, start_frame=goto, handoff_to_pipeline=True)
        status = "FAILED" if (not ok or not isinstance(res, dict)) else str(res.get("status", "FAILED")).upper()

        if status == "RUNNING":
            self._detect_attempts += 1
            print(f"[Coord] DETECT → RUNNING ({self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[Coord] DETECT Timebox erreicht → force TRACK")
                self._state = "TRACK"
            return {"RUNNING_MODAL"}

        # Triplet-Grouping defensiv
        ok_tg, tg = _safe_call(run_triplet_grouping, context)
        if ok_tg:
            print(f"[Coord] TRIPLET_GROUPING → {tg}")
        else:
            print(f"[Coord] TRIPLET_GROUPING failed: {tg!r}")

        print(f"[Coord] DETECT → {status} → TRACK (bidi)")
        self._state = "TRACK"
        return {"RUNNING_MODAL"}

    def _state_track(self, context):
        scn = context.scene

        if not self._bidi_started:
            scn[_BIDI_ACTIVE_KEY] = False
            print("[Coord] TRACK → launch clip.bidirectional_track (INVOKE_DEFAULT)")
            ok, _ = _safe_ops_invoke("clip.bidirectional_track", 'INVOKE_DEFAULT')
            if ok:
                self._bidi_started = True
            else:
                print("[Coord] TRACK launch failed → CLEAN_SHORT")
                self._bidi_started = False
                self._state = "CLEAN_SHORT"
            return {"RUNNING_MODAL"}

        if scn.get(_BIDI_ACTIVE_KEY, False):
            return {"RUNNING_MODAL"}

        # Ergebnisflag (optional)
        result = str(scn.get(_BIDI_RESULT_KEY, "") or "").upper()
        scn[_BIDI_RESULT_KEY] = ""
        self._bidi_started = False
        print(f"[Coord] TRACK → finished (result={result or 'NONE'}) → CLEAN_SHORT")
        self._state = "CLEAN_SHORT"
        return {"RUNNING_MODAL"}

    def _state_clean_short(self, context):
        try:
            frames_min = int(getattr(context.scene, "frames_track", 25) or 25)
            clean_short_tracks(context, min_len=frames_min, verbose=True)
            print(f"[Coord] CLEAN_SHORT → clean_short_tracks(min_len={frames_min})")
        except TypeError:
            clean_short_tracks(context)
            print("[Coord] CLEAN_SHORT → clean_short_tracks() fallback")
        except Exception as ex:
            print(f"[Coord] CLEAN_SHORT failed: {ex!r}")

        print("[Coord] CLEAN_SHORT → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    # ---------------- SPIKE → SOLVE → EVAL → (REFINE_LAUNCH → REFINE_WAIT → SOLVE → EVAL) → (CLEANUP → FIND_LOW) ----------------

    def _state_spike(self, context):
        if not self._spike_run_done:
            try:
                res = run_spike_filter_cycle(context, track_threshold=float(self._spike_threshold))
                print(f"[Coord] SPIKE → result={res}")
            except Exception as ex:
                print(f"[Coord] SPIKE failed: {ex!r}")
            self._spike_run_done = True

        print("[Coord] SPIKE → SOLVE")
        self._pending_eval_after_solve = True
        self._state = "SOLVE"
        return {"RUNNING_MODAL"}

    def _state_solve(self, context):
        try:
            _ = solve_camera_only(context)
            print("[Coord] SOLVE invoked")
        except Exception as ex:
            print(f"[Coord] SOLVE failed: {ex!r}")
        self._state = "EVAL" if self._pending_eval_after_solve else "FINALIZE"
        return {"RUNNING_MODAL"}

    def _state_eval(self, context):
        # Zielschwelle
        target = _scene_float(context.scene, "error_track", 0.0)
        wait_s = _scene_float(context.scene, "solve_wait_timeout_s", _DEFAULT_SOLVE_WAIT_S)

        curr = _wait_for_valid_reconstruction(context, timeout_s=wait_s)
        curr = _current_solve_error(context) if curr is None else curr
        print(f"[Coord] EVAL → curr_error={curr if curr is not None else 'None'} target={target}")

        if target > 0.0 and curr is not None and curr <= target:
            print("[Coord] EVAL → OK (≤ target) → FINALIZE")
            # Reset Cycle-Flags
            self._pending_eval_after_solve = False
            self._did_refine_this_cycle = False
            self._spike_run_done = False
            self._state = "FINALIZE"
        else:
            if self._did_refine_this_cycle:
                print("[Coord] EVAL → still above target after REFINE → CLEANUP")
                self._state = "CLEANUP"
            else:
                print("[Coord] EVAL → above target → REFINE_LAUNCH")
                self._state = "REFINE_LAUNCH"
        return {"RUNNING_MODAL"}

    def _state_refine_launch(self, context):
        """Startet Refine modal; wechselt in REFINE_WAIT und blockiert dort bis Ende/Timeout."""
        thr = _scene_float(context.scene, "error_track", 0.0)
        if thr <= 0.0:
            curr = _current_solve_error(context)
            thr = float(curr) if curr is not None else 0.0

        try:
            res = start_refine_modal(
                context,
                error_track=float(thr),
                only_selected_tracks=False,
                wait_seconds=0.05,
                ui_sleep_s=0.04,
                max_refine_calls=int(getattr(context.scene, "refine_max_calls", 20) or 20),
                tracking_object_name=None,
            )
            print(f"[Coord] REFINE_LAUNCH → {res}")
        except Exception as ex:
            print(f"[Coord] REFINE_LAUNCH failed (ignored): {ex!r}")
            res = {"status": "ERROR", "reason": repr(ex)}

        status = (res or {}).get("status", "").upper()
        timeout_s = _scene_float(context.scene, "refine_timeout_s", _DEFAULT_REFINE_TIMEOUT_S)
        self._refine_deadline = time.monotonic() + float(timeout_s)

        if status in ("STARTED", "BUSY"):
            # BUSY: bereits aktiv → trotzdem warten
            self._state = "REFINE_WAIT"
            return {"RUNNING_MODAL"}

        # NOT_STARTED/ERROR → kein aktiver Refine; direkt zum Re-Solve
        print("[Coord] REFINE_LAUNCH → not active → SOLVE")
        self._did_refine_this_cycle = False
        self._pending_eval_after_solve = True
        self._state = "SOLVE"
        return {"RUNNING_MODAL"}

    def _state_refine_wait(self, context):
        """Wartet bis der modal Refiner fertig ist (scene['refine_active'] == False) oder Timeout."""
        active = bool(context.scene.get("refine_active", False))
        now = time.monotonic()
        if not active:
            print("[Coord] REFINE_WAIT → finished → SOLVE")
            self._did_refine_this_cycle = True
            self._pending_eval_after_solve = True
            self._state = "SOLVE"
            return {"RUNNING_MODAL"}

        if self._refine_deadline is not None and now >= float(self._refine_deadline):
            print("[Coord] REFINE_WAIT → TIMEOUT → SOLVE (fallback)")
            self._did_refine_this_cycle = True  # wir haben versucht zu refinen
            self._pending_eval_after_solve = True
            self._state = "SOLVE"
            return {"RUNNING_MODAL"}

        # weiter warten
        return {"RUNNING_MODAL"}

    def _state_cleanup(self, context):
        # Optional: mit aktuellem Error limitieren, falls vorhanden
        limit = _current_solve_error(context)
        kwargs = {"wait_for_error": False, "action": "DELETE_TRACK"}
        if limit is not None:
            kwargs["error_limit"] = float(limit)

        ok, res = _safe_call(run_projection_cleanup_builtin, context, **kwargs)
        if ok:
            print(f"[Coord] CLEANUP → {res}")
        else:
            print(f"[Coord] CLEANUP failed: {res!r}")

        print("[Coord] CLEANUP → FIND_LOW (back to loop)")
        # Reset Flags für nächsten Loop
        self._spike_run_done = False
        self._pending_eval_after_solve = False
        self._did_refine_this_cycle = False
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    # ---------------- Modal-Wrapper ----------------
    def modal(self, context, event):
        try:
            if event.type == "ESC":
                return self._finish(context, cancelled=True)
            if event.type != "TIMER":
                return {"PASS_THROUGH"}

            if context.scene.get(_LOCK_KEY, False):
                return {"RUNNING_MODAL"}

            s = self._state
            if s == "INIT":
                return self._state_init(context)
            elif s == "FIND_LOW":
                return self._state_find_low(context)
            elif s == "JUMP":
                return self._state_jump(context)
            elif s == "DETECT":
                return self._state_detect(context)
            elif s == "TRACK":
                return self._state_track(context)
            elif s == "CLEAN_SHORT":
                return self._state_clean_short(context)
            elif s == "SPIKE":
                return self._state_spike(context)
            elif s == "SOLVE":
                return self._state_solve(context)
            elif s == "EVAL":
                return self._state_eval(context)
            elif s == "REFINE_LAUNCH":
                return self._state_refine_launch(context)
            elif s == "REFINE_WAIT":
                return self._state_refine_wait(context)
            elif s == "CLEANUP":
                return self._state_cleanup(context)
            elif s == "FINALIZE":
                return self._finish(context, cancelled=False)

            _tco_log(f"Unknown state '{s}' → FINALIZE")
            return self._finish(context, cancelled=False)

        except Exception as ex:  # noqa: BLE001
            _tco_log(f"modal: unexpected exception: {ex!r}")
            return self._finish(context, cancelled=True)

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
    register_scene_state()
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    unregister_scene_state()
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)


if __name__ == "__main__" and os.getenv("ADDON_RUN_TESTS", "0") == "1":
    print("[SelfTest] basic import OK")
