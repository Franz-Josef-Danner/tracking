from __future__ import annotations
"""
Tracking-Orchestrator – mit Feedback-Auswertung
-----------------------------------
FSM nutzt konsequent die Rückmeldungen der Helper:
- Detect: wartet solange RUNNING
- Bidirectional Track: wartet solange scene["bidi_active"] True ist
- Danach geht es weiter nach CLEAN_SHORT usw.
"""

import bpy
from typing import Optional, Dict

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8

_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator"
    bl_options = {"REGISTER", "UNDO"}

    use_apply_settings: bpy.props.BoolProperty(  # type: ignore
        name="Apply Tracker Defaults",
        default=True,
    )
    do_backward: bpy.props.BoolProperty(  # type: ignore
        name="Bidirectional",
        default=True,
    )
    auto_clean_short: bpy.props.BoolProperty(  # type: ignore
        name="Auto Clean Short",
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

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self._bootstrap(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        _safe_report(self, {"INFO"}, "Coordinator gestartet")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if context.scene.get(_LOCK_KEY, False):
            return {"RUNNING_MODAL"}

        if self._state == "INIT":
            return self._state_init(context)
        elif self._state == "FIND_LOW":
            return self._state_find_low(context)
        elif self._state == "JUMP":
            return self._state_jump(context)
        elif self._state == "DETECT":
            return self._state_detect(context)
        elif self._state == "TRACK_FWD":
            return self._state_track_fwd(context)
        elif self._state == "TRACK_BWD":
            return self._state_track_bwd(context)
        elif self._state == "CLEAN_SHORT":
            return self._state_clean_short(context)
        elif self._state == "FINALIZE":
            return self._finish(context, cancelled=False)
        return self._finish(context, cancelled=True)

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

    def _state_init(self, context):
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _state_find_low(self, context):
        from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
        result = run_find_low_marker_frame(context)
        status = str(result.get("status", "FAILED")).upper()
        if status == "FOUND":
            context.scene[_GOTO_KEY] = int(result.get("frame", context.scene.frame_current))
            self._jump_done = False
            self._state = "JUMP"
        elif status == "NONE":
            self._state = "FINALIZE"
        else:
            context.scene[_GOTO_KEY] = context.scene.frame_current
            self._jump_done = False
            self._state = "JUMP"
        return {"RUNNING_MODAL"}

    def _state_jump(self, context):
        from ..Helper.jump_to_frame import run_jump_to_frame  # type: ignore
        if not self._jump_done:
            run_jump_to_frame(context, frame=int(context.scene.get(_GOTO_KEY)), repeat_map=self._repeat_map)
            self._jump_done = True
        self._state = "DETECT"
        return {"RUNNING_MODAL"}

    def _state_detect(self, context):
        from ..Helper.detect import run_detect_once  # type: ignore
        result = run_detect_once(context, start_frame=int(context.scene.get(_GOTO_KEY, context.scene.frame_current)))
        status = str(result.get("status", "FAILED")).upper()
        if status == "RUNNING":
            self._detect_attempts += 1
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                self._state = "TRACK_FWD"
            return {"RUNNING_MODAL"}
        self._detect_attempts = 0
        self._state = "TRACK_FWD"
        return {"RUNNING_MODAL"}

    def _state_track_fwd(self, context):
        try:
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
        except Exception as ex:
            _safe_report(self, {"WARNING"}, f"TrackFwd Fehler: {ex}")
        if self.do_backward:
            self._state = "TRACK_BWD"
            self._bidi_started = False
        else:
            self._state = "CLEAN_SHORT"
        return {"RUNNING_MODAL"}

    def _state_track_bwd(self, context):
        scn = context.scene
        if not self._bidi_started:
            bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
            self._bidi_started = True
            return {"RUNNING_MODAL"}
        if scn.get(_BIDI_ACTIVE_KEY, False):
            return {"RUNNING_MODAL"}
        result = str(scn.get(_BIDI_RESULT_KEY, "") or "").upper()
        scn[_BIDI_RESULT_KEY] = ""
        self._state = "CLEAN_SHORT"
        return {"RUNNING_MODAL"}

    def _state_clean_short(self, context):
        if self.auto_clean_short:
            from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore
            frames = int(getattr(context.scene, "frames_track", 25) or 25)
            clean_short_tracks(context, min_len=frames, action="DELETE_TRACK", respect_fresh=True, verbose=True)
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _finish(self, context, *, cancelled: bool):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        context.scene[_LOCK_KEY] = False
        return {"CANCELLED" if cancelled else "FINISHED"}


def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
