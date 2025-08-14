import bpy
import time

from ..Helper.marker_helper_main import marker_helper_main
from ..Helper.main_to_adapt import main_to_adapt
from ..Helper.tracker_settings import apply_tracker_settings

class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Pipeline)"
    bl_options = {'REGISTER', 'UNDO'}

    use_apply_settings: bpy.props.BoolProperty(
        name="Apply Tracker Defaults",
        default=True,
        description="Apply tracker settings before running the pipeline",
    )
    do_backward: bpy.props.BoolProperty(
        name="Bidirectional",
        default=True,
        description="Run backward tracking after forward pass",
    )
    auto_clean_short: bpy.props.BoolProperty(
        name="Auto Clean Short",
        default=True,
        description="Delete short tracks after bidirectional tracking",
    )
    poll_every: bpy.props.FloatProperty(
        name="Poll Every (s)",
        default=0.05,
        min=0.01,
        description="Modal poll period",
    )

    _state: str = "INIT"
    _started_op: bool = False
    _fwd_done: bool = False
    _bwd_done: bool = False

    def _log(self, msg):
        print(f"[Coordinator] {msg}")

    def _activate_flag(self, context):
        context.scene["orchestrator_active"] = True

    def _deactivate_flag(self, context):
        context.scene["orchestrator_active"] = False

    def _remove_timer(self, context):
        try:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
        except Exception:
            pass

    def _cancel(self, context, reason="Cancelled"):
        self._log(f"Abbruch: {reason}")
        self._remove_timer(context)
        try:
            self._deactivate_flag(context)
        except Exception:
            pass
        self._state = "DONE"
        return {'CANCELLED'}

    def _bootstrap(self, context):
        self._state = "INIT"
        self._started_op = False
        self._fwd_done = False
        self._bwd_done = False

        self._detect_attempts = 0
        self._detect_attempts_max = 8

        try:
            ok, adapt_val, op_result = marker_helper_main(context)
            self._log(f"[MarkerHelper] → main_to_adapt: ok={ok}, adapt={adapt_val}, op_result={op_result}")
        except Exception as ex:
            self._log(f"[MarkerHelper] Fehler: {ex}")

        try:
            res = main_to_adapt(context, use_override=True)
            self._log(f"[MainToAdapt] Übergabe an tracker_settings (Helper) → {res}")
        except Exception as ex:
            self._log(f"[MainToAdapt] Fehler: {ex}")

        if self.use_apply_settings:
            try:
                apply_tracker_settings(context)
            except Exception as ex:
                self._log(f"[TrackerSettings] Fehler beim Anwenden der Defaults: {ex}")

        self._activate_flag(context)
        self._state = "FIND_LOW"

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "CLIP_EDITOR"

    def invoke(self, context, event):
        self._bootstrap(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_every, window=context.window)
        context.window_manager.modal_handler_add(self)
        self._log("Start")
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return self.invoke(context, None)

    def modal(self, context, event):
        if event.type == 'ESC':
            return self._cancel(context, "ESC gedrückt")

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if not context.area or context.area.type != "CLIP_EDITOR":
            return self._cancel(context, "CLIP_EDITOR-Kontext verloren")

        if self._state == "INIT":
            self._state = "FIND_LOW"
            return {'RUNNING_MODAL'}

        elif self._state == "FIND_LOW":
            try:
                from ..Helper.find_low_marker_frame import run_find_low_marker_frame
                res = run_find_low_marker_frame(context)
            except Exception as ex:
                self._log(f"[FindLow] Fehler: {ex}")
                res = {"status": "FAILED"}

            st = (res or {}).get("status", "FAILED")
            if st == "FOUND":
                context.scene["goto_frame"] = int(res.get("frame", context.scene.frame_current))
                self._state = "JUMP_DETECT"
            elif st == "NONE":
                self._state = "SOLVE"
            else:
                # Im Fehlerfall trotzdem versuchen weiterzumachen
                self._state = "JUMP_DETECT"
            return {'RUNNING_MODAL'}

        elif self._state == "JUMP_DETECT":
            goto = int(context.scene.get("goto_frame", context.scene.frame_current))
            try:
                from ..Helper.jump_to_frame import run_jump_to_frame
                run_jump_to_frame(context, frame=goto)
            except Exception:
                pass

            try:
                from ..Helper.detect import run_detect_once
                res = run_detect_once(context, start_frame=goto)
            except Exception as ex:
                res = {"status": "FAILED", "reason": f"exception:{ex}"}

            st = res.get("status", "FAILED")

            if st == "READY":
                self._started_op = False
                self._fwd_done = False
                self._bwd_done = False
                self._detect_attempts = 0
                self._state = "TRACK_FWD"
                return {'RUNNING_MODAL'}

            if st == "RUNNING":
                self._detect_attempts += 1
                if self._detect_attempts >= self._detect_attempts_max:
                    self._log("[Detect] Timebox erreicht – weiter mit TRACK_FWD.")
                    self._detect_attempts = 0
                    self._state = "TRACK_FWD"
                return {'RUNNING_MODAL'}

            self._log(f"[Detect] FAILED – {res.get('reason','')} → Fallback TRACK_FWD")
            self._detect_attempts = 0
            self._state = "TRACK_FWD"
            return {'RUNNING_MODAL'}

        elif self._state == "TRACK_FWD":
            try:
                bpy.ops.clip.track_markers(backwards=False)
            except Exception as ex:
                self._log(f"[TrackFwd] Fehler: {ex}")
            self._fwd_done = True
            self._state = "TRACK_BWD" if self.do_backward else "CLEAN_SHORT"
            return {'RUNNING_MODAL'}

        elif self._state == "TRACK_BWD":
            if self.do_backward:
                try:
                    bpy.ops.clip.track_markers(backwards=True)
                except Exception as ex:
                    self._log(f"[TrackBwd] Fehler: {ex}")
            self._bwd_done = True
            self._state = "CLEAN_SHORT"
            return {'RUNNING_MODAL'}

        elif self._state == "CLEAN_SHORT":
            if self.auto_clean_short:
                try:
                    from ..Helper.clean_short_tracks import clean_short_tracks
                    clean_short_tracks(context, action='DELETE_TRACK')
                except Exception as ex:
                    self._log(f"[CleanShort] Fehler: {ex}")
            self._state = "FIND_LOW"
            return {'RUNNING_MODAL'}

        elif self._state == "SOLVE":
            try:
                from ..Helper.solve_camera import run_solve_watch_clean
                run_solve_watch_clean(context)
            except Exception as ex:
                self._log(f"[Solve] Fehler: {ex}")
            self._deactivate_flag(context)
            self._state = "DONE"
            return {'FINISHED'}

        elif self._state == "DONE":
            self._remove_timer(context)
            self._deactivate_flag(context)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}


classes = (CLIP_OT_tracking_coordinator,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
