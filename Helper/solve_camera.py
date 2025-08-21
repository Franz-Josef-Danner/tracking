"""
Tracking-Orchestrator (SIMPLIFIED + POST-CLEAN, robustes Pre-Flight)
-------------------------------------------------------------------
FSM: INIT → FIND_LOW → JUMP → DETECT → TRACK → (Loop) …
Wenn Helper/find_low_marker_frame.py **NONE** liefert → SOLVE.
Nach dem Solve prüft der Coordinator auf ein POST-CLEAN-Signal (vom Solver):
  - wenn gesetzt → zuerst Helper/projection_cleanup_builtin.py mit übermittelter Schwelle (AvgErr), dann zurück zu FIND_LOW
  - sonst FINALIZE.

Neu / Fix:
- Pre-Flight-Helper werden **synchron bereits in invoke()** ausgeführt (vor dem Timer),
  mit sicherem CLIP_EDITOR-Kontext (temp_override). Dadurch „greifen“ die Einstellungen sofort.
- Doppelte Ausführung im State INIT wird vermieden via Flag _preflight_done.
- Pre-Flight nutzt robusten Fallback (Funktions-API → Operator), mit klaren Logs.
"""
from __future__ import annotations

import bpy
from typing import Optional, Dict, Tuple

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

# Scene Keys
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8

_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"

# Optimizer-Signal (von jump_to_frame)
_OPT_REQ_KEY = "__optimize_request"
_OPT_REQ_VAL = "JUMP_REPEAT"
_OPT_FRAME_KEY = "__optimize_frame"

# POST-CLEAN Signal (vom Solver gesetzt)
_POST_REQ_KEY = "__post_cleanup_request"
_POST_THR_KEY = "__post_cleanup_threshold"


# ---------------- Helpers ----------------

def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


def _find_clip_window(context) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None, None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            if region_window:
                return area, region_window, area.spaces.active
    return None, None, None


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Simplified + Post-Clean)"
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
    _preflight_done: bool = False

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    # ---------------- Lifecycle ----------------

    def _run_pre_flight_helpers(self, context) -> None:
        """Führt Marker-/Tracker-Setup **mit sicherem CLIP_EDITOR-Kontext** aus."""
        area, region, space = _find_clip_window(context)
        if not area:
            print("[Coord] BOOTSTRAP WARN: Kein CLIP_EDITOR für Pre-Flight verfügbar.")
            return

        def _call_marker_helper():
            try:
                from ..Helper.marker_helper_main import run_marker_helper_main  # type: ignore
                run_marker_helper_main(context)
                print("[Coord] BOOTSTRAP → marker_helper_main OK (run_*)")
                return True
            except Exception as ex_func:
                print(f"[Coord] BOOTSTRAP WARN: run_marker_helper_main failed: {ex_func!r}")
                try:
                    bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')
                    print("[Coord] BOOTSTRAP → marker_helper_main OK (operator)")
                    return True
                except Exception as ex_op:
                    print(f"[Coord] BOOTSTRAP INFO: marker_helper_main operator failed: {ex_op!r}")
            # optionaler direkter Fallback
            try:
                from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
                marker_helper_main(context)
                print("[Coord] BOOTSTRAP → marker_helper_main OK (direct)")
                return True
            except Exception as ex_func2:
                print(f"[Coord] BOOTSTRAP INFO: marker_helper_main direct failed: {ex_func2!r}")
            return False

        def _call_tracker_settings():
            try:
                from ..Helper.tracker_settings import apply_tracker_settings  # type: ignore
                apply_tracker_settings(context, log=True)
                print("[Coord] BOOTSTRAP → tracker_settings OK")
                return True
            except Exception as ex:
                print(f"[Coord] BOOTSTRAP WARN: tracker_settings failed: {ex!r}")
                try:
                    bpy.ops.clip.apply_tracker_settings('INVOKE_DEFAULT')
                    print("[Coord] BOOTSTRAP → apply_tracker_settings operator OK")
                    return True
                except Exception as ex2:
                    print(f"[Coord] BOOTSTRAP INFO: apply_tracker_settings operator failed: {ex2!r}")
            return False

        def _call_apply_defaults():
            if not self.use_apply_settings:
                return False
            try:
                from ..Helper.apply_tracker_settings import apply_tracker_settings  # type: ignore
                apply_tracker_settings(context)
                print("[Coord] BOOTSTRAP → apply_tracker_settings() OK")
                return True
            except Exception as ex:
                print(f"[Coord] BOOTSTRAP INFO: apply_tracker_settings not available/failed: {ex!r}")
            return False

        # Mit sicherem Override ausführen, damit Operatoren sauberen Kontext haben
        with context.temp_override(area=area, region=region, space_data=space):
            # Reihenfolge: tracker_defaults → marker_helper_main → apply_defaults(optional)
            _call_tracker_settings()
            _call_marker_helper()
            _call_apply_defaults()

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self._bootstrap(context)
        # PRE-FLIGHT SOFORT (synchron) AUSFÜHREN
        try:
            self._run_pre_flight_helpers(context)
            self._preflight_done = True
        except Exception as ex:
            print(f"[Coord] PRE-FLIGHT Exception: {ex!r}")
            self._preflight_done = False

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        _safe_report(self, {"INFO"}, "Coordinator (Simplified+PostClean) gestartet")
        print("[Coord] START (Detect→BiTrack) – Solve sobald FIND_LOW=NONE")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # Detect-Lock (kritische Sektion in Helper/detect.py)
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
        elif self._state == "SOLVE":
            return self._state_solve(context)
        elif self._state == "FINALIZE":
            return self._finish(context, cancelled=False)

        return self._finish(context, cancelled=True)

    # ---------------- Bootstrap ----------------

    def _bootstrap(self, context):
        scn = context.scene
        scn[_LOCK_KEY] = False
        scn[_BIDI_ACTIVE_KEY] = False
        scn[_BIDI_RESULT_KEY] = ""
        scn.pop(_POST_REQ_KEY, None)
        scn.pop(_POST_THR_KEY, None)
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False
        self._preflight_done = False

    # ---------------- States ----------------

    def _state_init(self, context):
        print("[Coord] INIT → BOOTSTRAP")
        if not self._preflight_done:
            print("[Coord] INIT → Pre-Flight nachholen …")
            self._run_pre_flight_helpers(context)
            self._preflight_done = True
        print("[Coord] BOOTSTRAP/Pre-Flight OK → FIND_LOW")
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
            print("[Coord] FIND_LOW → NONE → SOLVE (direkt)")
            self._state = "SOLVE"

        else:
            context.scene[_GOTO_KEY] = context.scene.frame_current
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FAILED ({result.get('reason', '?')}) → JUMP (best-effort)")
            self._state = "JUMP"

        return {"RUNNING_MODAL"}

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

            # Optional: Optimizer-Signal respektieren
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
        res = run_detect_once(
            context,
            start_frame=goto,
            handoff_to_pipeline=True,
        )
        status = str(res.get("status", "FAILED")).upper()

        if status == "RUNNING":
            self._detect_attempts += 1
            print(f"[Coord] DETECT → RUNNING (attempt {self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[Coord] DETECT Timebox erreicht → force TRACK")
                self._state = "TRACK"
            return {"RUNNING_MODAL"}

        self._detect_attempts = 0
        print(f"[Coord] DETECT → {status} → TRACK (Bidirectional)")
        self._state = "TRACK"
        return {"RUNNING_MODAL"}

    def _state_track(self, context):
        scn = context.scene

        if not self._bidi_started:
            scn[_BIDI_RESULT_KEY] = ""
            scn[_BIDI_ACTIVE_KEY] = False
            print("[Coord] TRACK → launch clip.bidirectional_track (INVOKE_DEFAULT)")
            try:
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                self._bidi_started = True
            except Exception as ex:
                print(f"[Coord] TRACK launch failed: {ex!r} → FIND_LOW (best-effort)")
                self._bidi_started = False
                self._state = "FIND_LOW"
            return {"RUNNING_MODAL"}

        if scn.get(_BIDI_ACTIVE_KEY, False):
            print("[Coord] TRACK → waiting (bidi_active=True)")
            return {"RUNNING_MODAL"}

        result = str(scn.get(_BIDI_RESULT_KEY, "") or "").upper()
        scn[_BIDI_RESULT_KEY] = ""
        self._bidi_started = False
        print(f"[Coord] TRACK → finished (result={result or 'NONE'}) → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _state_solve(self, context):
        scn = context.scene
        try:
            from ..Helper.solve_camera import solve_watch_clean  # type: ignore
            print("[Coord] SOLVE → solve_watch_clean() (Operator INVOKE_DEFAULT inside)")
            solve_watch_clean(context)
        except Exception as ex:
            print(f"[Coord] SOLVE failed: {ex!r}")
            return self._finish(context, cancelled=True)

        # Post-Cleanup-Signal prüfen
        post_req = bool(scn.get(_POST_REQ_KEY, False))
        post_thr = float(scn.get(_POST_THR_KEY, -1.0) or -1.0)
        if post_req and post_thr > 0.0:
            print(f"[Coord] SOLVE → POST-CLEAN request erkannt (threshold={post_thr:.6f})")
            try:
                from ..Helper.projection_cleanup_builtin import builtin_projection_cleanup  # type: ignore
                scn[_POST_THR_KEY] = float(post_thr)
                report = builtin_projection_cleanup(
                    context,
                    error_key=_POST_THR_KEY,
                    factor=1.0,
                    frames=0,
                    action='DELETE_TRACK',
                    dry_run=False,
                )
                print("[Coord] POST-CLEAN report:", {k: report.get(k) for k in ("affected", "threshold", "action")})
            except Exception as ex:
                print(f"[Coord] POST-CLEAN failed: {ex!r}")
            finally:
                scn.pop(_POST_REQ_KEY, None)
                # Schwelle aufräumen, damit spätere Cleanups nicht versehentlich diesen Wert nehmen
                scn.pop(_POST_THR_KEY, None)
            print("[Coord] SOLVE → FIND_LOW (nach POST-CLEAN)")
            self._state = "FIND_LOW"
            return {"RUNNING_MODAL"}

        print("[Coord] SOLVE → FINALIZE (kein POST-CLEAN Signal)")
        self._state = "FINALIZE"
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

"""
Tracking-Orchestrator (SIMPLIFIED + POST-CLEAN, robustes Pre-Flight)
-------------------------------------------------------------------
FSM: INIT → FIND_LOW → JUMP → DETECT → TRACK → (Loop) …
Wenn Helper/find_low_marker_frame.py **NONE** liefert → SOLVE.
Nach dem Solve prüft der Coordinator auf ein POST-CLEAN-Signal (vom Solver):
  - wenn gesetzt → zuerst Helper/projection_cleanup_builtin.py mit übermittelter Schwelle (AvgErr), dann zurück zu FIND_LOW
  - sonst FINALIZE.

Neu / Fix:
- Pre-Flight-Helper werden **synchron bereits in invoke()** ausgeführt (vor dem Timer),
  mit sicherem CLIP_EDITOR-Kontext (temp_override). Dadurch „greifen“ die Einstellungen sofort.
- Doppelte Ausführung im State INIT wird vermieden via Flag _preflight_done.
- Pre-Flight nutzt robusten Fallback (Funktions-API → Operator), mit klaren Logs.
"""

import bpy
from typing import Optional, Dict, Tuple

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

# Scene Keys
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8

_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"

# Optimizer-Signal (von jump_to_frame)
_OPT_REQ_KEY = "__optimize_request"
_OPT_REQ_VAL = "JUMP_REPEAT"
_OPT_FRAME_KEY = "__optimize_frame"

# POST-CLEAN Signal (vom Solver gesetzt)
_POST_REQ_KEY = "__post_cleanup_request"
_POST_THR_KEY = "__post_cleanup_threshold"


# ---------------- Helpers ----------------

def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


def _find_clip_window(context) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None, None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            if region_window:
                return area, region_window, area.spaces.active
    return None, None, None


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Simplified + Post-Clean)"
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
    _preflight_done: bool = False

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    # ---------------- Lifecycle ----------------

    def _run_pre_flight_helpers(self, context) -> None:
        """Führt Marker-/Tracker-Setup **mit sicherem CLIP_EDITOR-Kontext** aus."""
        area, region, space = _find_clip_window(context)
        if not area:
            print("[Coord] BOOTSTRAP WARN: Kein CLIP_EDITOR für Pre-Flight verfügbar.")
            return

        def _call_marker_helper():
            try:
                from ..Helper.marker_helper_main import run_marker_helper_main  # type: ignore
                run_marker_helper_main(context)
                print("[Coord] BOOTSTRAP → marker_helper_main OK (run_*)")
                return True
            except Exception as ex_func:
                print(f"[Coord] BOOTSTRAP WARN: run_marker_helper_main failed: {ex_func!r}")
                try:
                    bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')
                    print("[Coord] BOOTSTRAP → marker_helper_main OK (operator)")
                    return True
                except Exception as ex_op:
                    print(f"[Coord] BOOTSTRAP INFO: marker_helper_main operator failed: {ex_op!r}")
            # optionaler direkter Fallback
            try:
                from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
                marker_helper_main(context)
                print("[Coord] BOOTSTRAP → marker_helper_main OK (direct)")
                return True
            except Exception as ex_func2:
                print(f"[Coord] BOOTSTRAP INFO: marker_helper_main direct failed: {ex_func2!r}")
            return False

        def _call_tracker_settings():
            try:
                from ..Helper.tracker_settings import apply_tracker_settings  # type: ignore
                apply_tracker_settings(context, log=True)
                print("[Coord] BOOTSTRAP → tracker_settings OK")
                return True
            except Exception as ex:
                print(f"[Coord] BOOTSTRAP WARN: tracker_settings failed: {ex!r}")
                try:
                    bpy.ops.clip.apply_tracker_settings('INVOKE_DEFAULT')
                    print("[Coord] BOOTSTRAP → apply_tracker_settings operator OK")
                    return True
                except Exception as ex2:
                    print(f"[Coord] BOOTSTRAP INFO: apply_tracker_settings operator failed: {ex2!r}")
            return False

        def _call_apply_defaults():
            if not self.use_apply_settings:
                return False
            try:
                from ..Helper.apply_tracker_settings import apply_tracker_settings  # type: ignore
                apply_tracker_settings(context)
                print("[Coord] BOOTSTRAP → apply_tracker_settings() OK")
                return True
            except Exception as ex:
                print(f"[Coord] BOOTSTRAP INFO: apply_tracker_settings not available/failed: {ex!r}")
            return False

        # Mit sicherem Override ausführen, damit Operatoren sauberen Kontext haben
        with context.temp_override(area=area, region=region, space_data=space):
            # Reihenfolge: tracker_defaults → marker_helper_main → apply_defaults(optional)
            _call_tracker_settings()
            _call_marker_helper()
            _call_apply_defaults()

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self._bootstrap(context)
        # PRE-FLIGHT SOFORT (synchron) AUSFÜHREN
        try:
            self._run_pre_flight_helpers(context)
            self._preflight_done = True
        except Exception as ex:
            print(f"[Coord] PRE-FLIGHT Exception: {ex!r}")
            self._preflight_done = False

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        _safe_report(self, {"INFO"}, "Coordinator (Simplified+PostClean) gestartet")
        print("[Coord] START (Detect→BiTrack) – Solve sobald FIND_LOW=NONE")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # Detect-Lock (kritische Sektion in Helper/detect.py)
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
        elif self._state == "SOLVE":
            return self._state_solve(context)
        elif self._state == "FINALIZE":
            return self._finish(context, cancelled=False)

        return self._finish(context, cancelled=True)

    # ---------------- Bootstrap ----------------

    def _bootstrap(self, context):
        scn = context.scene
        scn[_LOCK_KEY] = False
        scn[_BIDI_ACTIVE_KEY] = False
        scn[_BIDI_RESULT_KEY] = ""
        scn.pop(_POST_REQ_KEY, None)
        scn.pop(_POST_THR_KEY, None)
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False
        self._preflight_done = False

    # ---------------- States ----------------

    def _state_init(self, context):
        print("[Coord] INIT → BOOTSTRAP")
        if not self._preflight_done:
            print("[Coord] INIT → Pre-Flight nachholen …")
            self._run_pre_flight_helpers(context)
            self._preflight_done = True
        print("[Coord] BOOTSTRAP/Pre-Flight OK → FIND_LOW")
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
            print("[Coord] FIND_LOW → NONE → SOLVE (direkt)")
            self._state = "SOLVE"

        else:
            context.scene[_GOTO_KEY] = context.scene.frame_current
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FAILED ({result.get('reason', '?')}) → JUMP (best-effort)")
            self._state = "JUMP"

        return {"RUNNING_MODAL"}

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

            # Optional: Optimizer-Signal respektieren
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
        res = run_detect_once(
            context,
            start_frame=goto,
            handoff_to_pipeline=True,
        )
        status = str(res.get("status", "FAILED")).upper()

        if status == "RUNNING":
            self._detect_attempts += 1
            print(f"[Coord] DETECT → RUNNING (attempt {self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[Coord] DETECT Timebox erreicht → force TRACK")
                self._state = "TRACK"
            return {"RUNNING_MODAL"}

        self._detect_attempts = 0
        print(f"[Coord] DETECT → {status} → TRACK (Bidirectional)")
        self._state = "TRACK"
        return {"RUNNING_MODAL"}

    def _state_track(self, context):
        scn = context.scene

        if not self._bidi_started:
            scn[_BIDI_RESULT_KEY] = ""
            scn[_BIDI_ACTIVE_KEY] = False
            print("[Coord] TRACK → launch clip.bidirectional_track (INVOKE_DEFAULT)")
            try:
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                self._bidi_started = True
            except Exception as ex:
                print(f"[Coord] TRACK launch failed: {ex!r} → FIND_LOW (best-effort)")
                self._bidi_started = False
                self._state = "FIND_LOW"
            return {"RUNNING_MODAL"}

        if scn.get(_BIDI_ACTIVE_KEY, False):
            print("[Coord] TRACK → waiting (bidi_active=True)")
            return {"RUNNING_MODAL"}

        result = str(scn.get(_BIDI_RESULT_KEY, "") or "").upper()
        scn[_BIDI_RESULT_KEY] = ""
        self._bidi_started = False
        print(f"[Coord] TRACK → finished (result={result or 'NONE'}) → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _state_solve(self, context):
        scn = context.scene
        try:
            from ..Helper.solve_camera import solve_watch_clean  # type: ignore
            print("[Coord] SOLVE → solve_watch_clean() (Operator INVOKE_DEFAULT inside)")
            solve_watch_clean(context)
        except Exception as ex:
            print(f"[Coord] SOLVE failed: {ex!r}")
            return self._finish(context, cancelled=True)

        # Post-Cleanup-Signal prüfen
        post_req = bool(scn.get(_POST_REQ_KEY, False))
        post_thr = float(scn.get(_POST_THR_KEY, -1.0) or -1.0)
        if post_req and post_thr > 0.0:
            print(f"[Coord] SOLVE → POST-CLEAN request erkannt (threshold={post_thr:.6f})")
            try:
                from ..Helper.projection_cleanup_builtin import builtin_projection_cleanup  # type: ignore
                scn[_POST_THR_KEY] = float(post_thr)
                report = builtin_projection_cleanup(
                    context,
                    error_key=_POST_THR_KEY,
                    factor=1.0,
                    frames=0,
                    action='DELETE_TRACK',
                    dry_run=False,
                )
                print("[Coord] POST-CLEAN report:", {k: report.get(k) for k in ("affected", "threshold", "action")})
            except Exception as ex:
                print(f"[Coord] POST-CLEAN failed: {ex!r}")
            finally:
                scn.pop(_POST_REQ_KEY, None)
                # Schwelle aufräumen, damit spätere Cleanups nicht versehentlich diesen Wert nehmen
                scn.pop(_POST_THR_KEY, None)
            print("[Coord] SOLVE → FIND_LOW (nach POST-CLEAN)")
            self._state = "FIND_LOW"
            return {"RUNNING_MODAL"}

        print("[Coord] SOLVE → FINALIZE (kein POST-CLEAN Signal)")
        self._state = "FINALIZE"
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
