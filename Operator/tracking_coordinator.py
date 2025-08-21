from __future__ import annotations
"""
Tracking-Orchestrator (SIMPLIFIED)
---------------------------------
Ablauf (FSM): INIT → FIND_LOW → JUMP → DETECT (READY/FAILED zählen; RUNNING timeboxed) → TRACK (bidirectional, modal) → zurück zu FIND_LOW …
Sobald Helper/find_low_marker_frame.py **keinen** Frame mit zu wenigen Markern mehr findet (Status "NONE"),
wird **sofort** Helper/solve_camera.py ausgelöst und der Orchestrator beendet.

Wichtig:
- KEIN Helper/clean_error_tracks.py mehr.
- KEIN Helper/clean_short_tracks.py mehr (Property entfernt).
- Coordinator ruft niemals direkt bpy.ops.clip.track_markers auf, sondern ausschließlich den Helper-Operator
  Helper/bidirectional_track.py (clip.bidirectional_track).
- Detect kann mehrfach (RUNNING) im selben State laufen, bis READY/FAILED oder Timebox (_MAX_DETECT_ATTEMPTS).

Bestehende Pre-Flight-Helper (tracker_settings, marker_helper_main, apply_tracker_settings) bleiben erhalten.
Optimizer-Signal via jump_to_frame wird weiterhin unterstützt.
"""

import bpy
from typing import Optional, Dict

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


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Simplified)"
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

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    # ---------------- Lifecycle ----------------

    def _run_pre_flight_helpers(self, context) -> None:
        # 1) tracker_settings.py
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

        # 2) marker_helper_main.py (Funktions-API bevorzugt)
        try:
            from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
            marker_helper_main(context)
            print("[Coord] BOOTSTRAP → marker_helper_main OK (run_*)")
        except Exception as ex_func:
            print(f"[Coord] BOOTSTRAP WARN: marker_helper_main failed: {ex_func!r}")
            try:
                bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')
            except Exception:
                pass

        # 2b) marker_helper_main.py (Fallback: direkte Funktions-API, falls vorhanden)
        try:
            from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
            marker_helper_main(context)
            print("[Coord] BOOTSTRAP → marker_helper_main OK (direct)")
        except Exception as ex_func2:
            print(f"[Coord] BOOTSTRAP INFO: marker_helper_main direct call not available/failed: {ex_func2!r}")

        # 3) (optional) Tracker-Defaults anwenden, wenn UI-Option aktiv
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
        _safe_report(self, {"INFO"}, "Coordinator (Simplified) gestartet")
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
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False

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
            # NEU: Direkt in SOLVE verzweigen, keinerlei Cleanups mehr
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
        """Akzeptiert READY/FAILED → TRACK, RUNNING → im DETECT-State bleiben (bis Timebox)."""
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
        """Startet und überwacht den Bidirectional-Operator; danach zurück zu FIND_LOW."""
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
        """Solve-Phase: Direkt nach FIND_LOW→NONE."""
        try:
            from ..Helper.solve_camera import solve_watch_clean  # type: ignore
            print("[Coord] SOLVE → solve_watch_clean()")
            solve_watch_clean(context)
        except Exception as ex:
            print(f"[Coord] SOLVE failed: {ex!r}")
            return self._finish(context, cancelled=True)
        print("[Coord] SOLVE → FINALIZE")
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
