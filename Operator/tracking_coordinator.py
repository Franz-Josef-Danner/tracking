from __future__ import annotations

import os
import time
import bpy
from bpy.types import Scene
from bpy.props import BoolProperty, FloatProperty
from typing import Optional, Dict
from typing import Any, Callable, Tuple

from ..Helper.triplet_grouping import run_triplet_grouping  # top-level import
from ..Helper.solve_camera import solve_camera_only
from ..Helper.projection_cleanup_builtin import run_projection_cleanup_builtin  # optional (derzeit ungenutzt)

# Cycle-Helpers
from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore
from ..Helper.find_max_marker_frame import run_find_max_marker_frame  # type: ignore
from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
from ..Helper.spike_filter_cycle import run_spike_filter_cycle  # type: ignore

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

# Cycle: Sicherheitslimit (äußeres Loop-Limit)
_CYCLE_MAX_LOOPS = 50


def _tco_log(msg: str) -> None:
    print(f"[tracking_coordinator] {msg}")


# ---------------------------------------------------------------------------
# Generische Guards / Utilities
# ---------------------------------------------------------------------------

def _safe_call(func: Callable[..., Any], *args, **kwargs) -> Tuple[bool, Any]:
    """Ruft eine Funktion sicher auf. Liefert (ok, result_or_exc)."""
    try:
        return True, func(*args, **kwargs)
    except Exception as ex:  # noqa: BLE001 - logging only
        _tco_log(f"_safe_call({getattr(func, '__name__', 'func')}): {ex!r}")
        return False, ex


def _safe_ops_invoke(ops_path: str, *args, **kwargs) -> Tuple[bool, Any]:
    """bpy.ops sicher aufrufen, z.B. _safe_ops_invoke('clip.bidirectional_track', 'INVOKE_DEFAULT')."""
    try:
        mod, name = ops_path.split(".", 1)
        ops_mod = getattr(bpy.ops, mod)
        op = getattr(ops_mod, name)
    except Exception as ex_resolve:  # noqa: BLE001
        _tco_log(f"_safe_ops_invoke: resolve failed for '{ops_path}': {ex_resolve!r}")
        return False, ex_resolve
    try:
        return True, op(*args, **kwargs)
    except Exception as ex_run:  # noqa: BLE001
        _tco_log(f"_safe_ops_invoke: call failed for '{ops_path}': {ex_run!r}")
        return False, ex_run


def _scene_float(scene: bpy.types.Scene, key: str, default: float) -> float:
    """Defensiver Float-Getter für Scene-Properties."""
    try:
        v = getattr(scene, key, default)
        v = default if v is None else v
        return float(v)
    except Exception:
        return float(default)


def _have_clip(context: bpy.types.Context) -> bool:
    space = getattr(context, "space_data", None)
    return bool(getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None))


# ---------------------------------------------------------------------------
# Optionales Spike-Value-Memo (für nachgelagerte Workflows)
# ---------------------------------------------------------------------------

def register_scene_state() -> None:
    if not hasattr(Scene, "tco_spike_value"):
        Scene.tco_spike_value = FloatProperty(
            name="Spike Filter Value",
            description=(
                "Finaler Wert für spike_filter_cycle, der nach Cleanup einmalig ausgelöst wird."
            ),
            default=0.0,
        )
    if not hasattr(Scene, "tco_spike_pending"):
        Scene.tco_spike_pending = BoolProperty(
            name="Spike Pending",
            description=(
                "True, wenn ein finaler Spike-Wert gemerkt wurde und auf Cleanup wartet."
            ),
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
    _tco_log(
        f"remember_spike_filter_value: value={scene.tco_spike_value:.6f}, pending=True"
    )


def on_projection_cleanup_finished(*, context: bpy.types.Context | None = None) -> None:
    ctx = context or bpy.context
    scene = ctx.scene
    if getattr(scene, "tco_spike_pending", False):
        value = float(getattr(scene, "tco_spike_value", 0.0))
        _tco_log(f"cleanup finished -> trigger spike once with value={value:.6f}")
        trigger_spike_filter_once(value, context=ctx)
        scene.tco_spike_pending = False
    else:
        _tco_log("cleanup finished, no pending spike value -> noop")


def trigger_spike_filter_once(value: float, *, context: bpy.types.Context | None = None) -> None:
    ctx = context or bpy.context
    scene = ctx.scene
    # Reentrancy-Guard: Verhindert, dass run_spike_filter_cycle am Ende wieder "pending" setzt
    scene["tco_spike_suppress_remember"] = True
    try:
        try:
            from ..Helper import spike_filter_cycle as _sfc  # lazy import
            if hasattr(_sfc, "run_with_value"):
                _sfc.run_with_value(ctx, float(value))
                return
        except Exception as ex:  # noqa: BLE001 - logging
            _tco_log(f"direct call failed: {ex!r}; fallback to bpy.ops")

        try:
            bpy.ops.helper.spike_filter_cycle("INVOKE_DEFAULT", value=float(value))
        except Exception as ex:  # noqa: BLE001 - logging
            _tco_log(f"bpy.ops fallback failed: {ex!r}")
    finally:
        # Flag immer zurücksetzen
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

    # --- Cycle-Bookkeeping ---
    _cycle_active: bool = False
    _cycle_stage: str = ""      # "CYCLE_FIND_LOW" | "CYCLE_FIND_MAX" | "CYCLE_SPIKE"
    _cycle_loops: int = 0        # Anzahl der durchlaufenen FIND_MAX↔SPIKE Runden
    _cycle_initial_clean_done: bool = False  # << nur einmal zu Beginn
    _cycle_spike_threshold: float = 100.0

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
        _safe_report(self, {"INFO"}, "Coordinator gestartet")
        print("[Coord] START (STRICT Detect→Bidi→CleanShort→Cycle→Solve)")
        return {"RUNNING_MODAL"}

    # ---------------- Bootstrap ----------------

    def _bootstrap(self, context):
        scn = context.scene
        scn[_LOCK_KEY] = False
        scn[_BIDI_ACTIVE_KEY] = False
        scn[_BIDI_RESULT_KEY] = ""
        scn.pop(_GOTO_KEY, None)
        scn.pop("__skip_clean_short_once", None)

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
        self._cycle_spike_threshold = float(getattr(context.scene, "spike_start_threshold", 100.0) or 100.0)

    # ---------------- States ----------------

    def _state_init(self, context):
        print("[Coord] INIT → BOOTSTRAP")
        self._run_pre_flight_helpers(context)
        print("[Coord] BOOTSTRAP → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _state_find_low(self, context):
        # defensiv: kein Clip → noop
        if not _have_clip(context):
            print("[Coord] FIND_LOW → no active clip → retry")
            return {"RUNNING_MODAL"}

        ok, result = _safe_call(run_find_low_marker_frame, context)
        if not ok or not isinstance(result, dict):
            print(f"[Coord] FIND_LOW → FAILED (exception/invalid result) → JUMP (best-effort)")
            result = {"status": "FAILED", "reason": "exception-or-invalid-result"}

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
            self._state = "CYCLE_CLEAN"

        else:
            context.scene[_GOTO_KEY] = context.scene.frame_current
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FAILED ({result.get('reason', '?')}) → JUMP (best-effort)")
            self._state = "JUMP"

        return {"RUNNING_MODAL"}

    # ---------------- SOLVE (NO-REFINE, NO-WAIT, NO-CLEANUP) ----------------

    def _state_solve(self, context):
        try:
            res = solve_camera_only(context)
            print(f"[Coord] SOLVE → invoked: {res}")
        except Exception as ex:
            print(f"[Coord] SOLVE start failed: {ex!r}")
        # Direkt finalisieren – keine Warte-/Refine-/Cleanup-Phase
        self._state = "FINALIZE"
        return {"RUNNING_MODAL"}

    # ---------------- JUMP/DETECT/TRACK/CLEAN_SHORT ----------------

    def _state_jump(self, context):
        from ..Helper.jump_to_frame import run_jump_to_frame  # type: ignore
        if not self._jump_done:
            goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
            ok, jr = _safe_call(run_jump_to_frame, context, frame=goto, repeat_map=self._repeat_map)
            if not ok or not isinstance(jr, dict):
                print(f"[Coord] JUMP failed: invalid result → FIND_LOW")
                self._state = "FIND_LOW"
                return {"RUNNING_MODAL"}
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
                    ok_opt, res_opt = _safe_call(start_optimization, context)
                    if ok_opt:
                        print(f"[Coord] JUMP → OPTIMIZE (start_optimization, frame={opt_frame})")
                    else:
                        print(f"[Coord] OPTIMIZE failed (function): {res_opt!r}")
                        ok_op, _ = _safe_ops_invoke("clip.optimize_tracking_modal", 'INVOKE_DEFAULT')
                        if ok_op:
                            print(f"[Coord] JUMP → OPTIMIZE (operator fallback, frame={opt_frame})")
                        else:
                            print("[Coord] OPTIMIZE launch failed (operator)")
                except Exception as ex_func:
                    print(f"[Coord] OPTIMIZE failed (function): {ex_func!r}")
                    ok_op, _ = _safe_ops_invoke("clip.optimize_tracking_modal", 'INVOKE_DEFAULT')
                    if ok_op:
                        print(f"[Coord] JUMP → OPTIMIZE (operator fallback, frame={opt_frame})")
                    else:
                        print("[Coord] OPTIMIZE launch failed (operator)")

            self._jump_done = True
        self._detect_attempts = 0
        self._state = "DETECT"
        return {"RUNNING_MODAL"}

    def _state_detect(self, context):
        from ..Helper.detect import run_detect_once  # type: ignore

        goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
        ok, res = _safe_call(run_detect_once, context, start_frame=goto, handoff_to_pipeline=True)
        if not ok or not isinstance(res, dict):
            print(f"[Coord] DETECT → exception/invalid result → treat as FAILED")
            status = "FAILED"
        else:
            status = str(res.get("status", "FAILED")).upper()

        if status == "RUNNING":
            self._detect_attempts += 1
            print(f"[Coord] DETECT → RUNNING (attempt {self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[Coord] DETECT Timebox erreicht → force TRACK")
                self._state = "TRACK"
            return {"RUNNING_MODAL"}

        # Triplet-Grouping defensiv (Fehler tolerieren, Flow unverändert)
        ok_tg, tg = _safe_call(run_triplet_grouping, context)
        if ok_tg:
            print(f"[Coord] TRIPLET_GROUPING → {tg}")
        else:
            print(f"[Coord] TRIPLET_GROUPING failed: {tg!r}")

        print(f"[Coord] DETECT → {status} → TRACK (Bidirectional)")
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
                print("[Coord] TRACK launch failed → CLEAN_SHORT (best-effort)")
                self._bidi_started = False
                self._state = "CLEAN_SHORT"
            return {"RUNNING_MODAL"}

        if scn.get(_BIDI_ACTIVE_KEY, False):
            print("[Coord] TRACK → waiting (bidi_active=True)")
            return {"RUNNING_MODAL"}

        # defensiver Zugriff auf Ergebnisflag
        try:
            result = str(scn.get(_BIDI_RESULT_KEY, "") or "").upper()
        except Exception:
            result = ""
        scn[_BIDI_RESULT_KEY] = ""
        self._bidi_started = False
        print(f"[Coord] TRACK → finished (result={result or 'NONE'}) → CLEAN_SHORT")
        self._state = "CLEAN_SHORT"
        return {"RUNNING_MODAL"}

    def _state_clean_short(self, context):
        # Bestandteil der ursprünglichen FSM
        print("[Coord] CLEAN_SHORT (no-op)")
        if self._cycle_active and self._cycle_stage == "CYCLE_SPIKE":
            print("[Coord] CLEAN_SHORT → CYCLE_SPIKE (cycle continuation)")
            self._state = "CYCLE_SPIKE"
        else:
            print("[Coord] CLEAN_SHORT → FIND_LOW")
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

    def _state_cycle_find_low(self, context):
        """Findet einen *niedrigen* Marker-Frame als neuen Startpunkt für den nächsten Cycle."""
        try:
            res = run_find_low_marker_frame(context)
            # Ergebnis normalisieren: dict- oder tuple-API unterstützen
            status = "FAILED"
            frame = None
            if isinstance(res, dict):
                status = str(res.get("status", "FAILED")).upper()
                frame = res.get("frame", None)
            elif isinstance(res, (list, tuple)) and len(res) >= 2:
                ok = bool(res[0])
                status = "FOUND" if ok else "NONE"
                frame = res[1]
            print(f"[Coord] CYCLE_FIND_LOW → res={res!r}")

            if status == "FOUND" and frame is not None:
                try:
                    frame_i = int(frame)
                except Exception:
                    raise ValueError(f"invalid frame value: {frame!r}")
                # Ziel über JUMP→DETECT→TRACK anfahren; SPIKE nur vormerken
                context.scene[_GOTO_KEY] = frame_i
                self._jump_done = False
                self._cycle_stage = "CYCLE_SPIKE"
                print(f"[Coord] CYCLE_FIND_LOW → FOUND frame={frame_i} → JUMP")
                self._state = "JUMP"
                return {"RUNNING_MODAL"}
        except Exception as ex:
            print(f"[Coord] CYCLE_FIND_LOW failed: {ex!r}")

        # Fallback-Pfad
        self._cycle_stage = "CYCLE_FIND_MAX"
        self._state = "CYCLE_FIND_MAX"
        return {"RUNNING_MODAL"}

    def _state_cycle_findmax(self, context):
        """FIND_MAX → bei FOUND: SOLVE, sonst SPIKE."""
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
        max_loops = int(getattr(context.scene, "cycle_max_loops", _CYCLE_MAX_LOOPS) or _CYCLE_MAX_LOOPS)
        if max_loops <= 0:
            print("[Coord] CYCLE_SPIKE → invalid max_loops ≤ 0 → FINALIZE")
            self._cycle_active = False
            self._cycle_stage = ""
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}

        if self._cycle_loops > max_loops:
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

    # ---------------- Modal-Wrapper ----------------
    def modal(self, context, event):
        try:
            if event.type == "ESC":
                return self._finish(context, cancelled=True)
            if event.type != "TIMER":
                return {"PASS_THROUGH"}

            # Detect-Lock respektieren (kritische Sektion in Helper/detect.py)
            if context.scene.get(_LOCK_KEY, False):
                return {"RUNNING_MODAL"}

            # FSM
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
            elif self._state == "CYCLE_CLEAN":
                return self._state_cycle_clean(context)
            elif self._state == "CYCLE_FIND_LOW":
                return self._state_cycle_find_low(context)
            elif self._state == "CYCLE_FIND_MAX":
                return self._state_cycle_findmax(context)
            elif self._state == "CYCLE_SPIKE":
                return self._state_cycle_spike(context)
            elif self._state == "FINALIZE":
                return self._finish(context, cancelled=False)
            return self._finish(context, cancelled=True)
        except Exception as ex:  # noqa: BLE001 - final guard
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
