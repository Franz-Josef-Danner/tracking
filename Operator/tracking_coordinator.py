
# Operator/tracking_coordinator.py
import bpy
import time

from ..Helper.marker_helper_main import marker_helper_main
from ..Helper.main_to_adapt import main_to_adapt
from ..Helper.tracker_settings import apply_tracker_settings
from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame
from ..Helper.detect import run_detect_once

try:
    from ..Helper.tracker_settings import apply_tracker_settings
except Exception:
    apply_tracker_settings = None
try:
    from ..Helper.clean_short_tracks import clean_short_tracks
except Exception:
    clean_short_tracks = None
try:
    from ..Helper.solve_camera import run_solve_watch_clean
except Exception:
    run_solve_watch_clean = None


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Orchestrator: determiniert die Tracking-Pipeline via State Machine.
    States: INIT -> FIND_LOW -> JUMP_DETECT -> TRACK_FWD -> TRACK_BWD -> CLEAN_SHORT -> FIND_LOW -> ... -> SOLVE -> DONE
    """
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
        name="Auto Clean Short Tracks",
        default=True,
        description="Delete/disable very short tracks after tracking passes",
    )
    target_min_markers: bpy.props.IntProperty(
        name="Min Markers per Frame",
        default=25,
        min=1, max=500,
    )
    frames_track: bpy.props.IntProperty(
        name="Frames per Tracking Burst",
        default=25,
        min=1, max=500,
    )
    poll_every: bpy.props.FloatProperty(
        name="Poll Interval (sec)",
        default=0.25,
        min=0.05, max=5.0,
    )

    _state = None
    _last_tick = 0.0
    _started_op = False
    _fwd_done = False
    _bwd_done = False

    def execute(self, context):
        self._bootstrap(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        self._bootstrap(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _bootstrap(self, context):
        """Initialisierungen und Helper-Aufrufe vor dem Pipeline-Start."""
        # 1. Marker-Helper: Ziel- und Grenzwerte berechnen
        marker_helper_main(context)
        # 2. adaptiven Marker-Wert anpassen
        main_to_adapt(context)
        # 3. Tracker-Defaults setzen
        apply_tracker_settings(context)
        # scene["marker_basis"] & frames_track werden wie gehabt gesetzt
        context.scene["marker_basis"] = int(self.target_min_markers)
        context.scene["frames_track"] = int(self.frames_track)
        # Flags für orchestrator_active etc. hier setzen
        context.scene["orchestrator_active"] = True
        # Initialen Zustand festlegen
        self._state = "FIND_LOW"

    def _deactivate_flag(self, context):
        try:
            context.scene["orchestrator_active"] = False
        except Exception:
            pass

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self._state = "DONE"
            self._deactivate_flag(context)
            self.report({'INFO'}, "Pipeline abgebrochen.")
            return {'CANCELLED'}

        now = time.time()
        if self._last_tick == 0.0 or (now - self._last_tick) >= float(self.poll_every):
            self._last_tick = now
        else:
            return {'PASS_THROUGH'}

        try:
            if self._state == "INIT":
                if self.use_apply_settings and apply_tracker_settings:
                    try:
                        apply_tracker_settings(context)
                        self.report({'INFO'}, "[SETTINGS] tracker defaults applied")
                    except Exception as ex:
                        self.report({'WARNING'}, f"[SETTINGS] failed: {ex}")
                self._state = "FIND_LOW"
                return {'RUNNING_MODAL'}

            if self._state == "FIND_LOW":
                low = run_find_low_marker_frame(context)
                low_frame = low.get("frame") if isinstance(low, dict) else low
                if low_frame is None:
                    self._state = "SOLVE"
                    return {'RUNNING_MODAL'}
                context.scene["goto_frame"] = int(low_frame)
                self.report({'INFO'}, f"[FIND_LOW] next low-marker frame: {low_frame}")
                self._state = "JUMP_DETECT"
                return {'RUNNING_MODAL'}

            if self._state == "JUMP_DETECT":
                run_jump_to_frame(context, frame=context.scene.get("goto_frame", None))
                try:
                    run_detect_once(context, start_frame=int(context.scene.get("goto_frame", 1)))
                except Exception:
                    pass
                self._started_op = False
                self._fwd_done = False
                self._bwd_done = False
                self._state = "TRACK_FWD"
                return {'RUNNING_MODAL'}

            if self._state == "TRACK_FWD":
                if not self._started_op:
                    try:
                        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
                        self.report({'INFO'}, "[TRACK_FWD] started (INVOKE_DEFAULT)")
                        self._started_op = True
                        return {'RUNNING_MODAL'}
                    except Exception as ex:
                        self.report({'WARNING'}, f"[TRACK_FWD] start failed: {ex}")
                        self._fwd_done = True
                if self._fwd_done:
                    self._state = "TRACK_BWD" if self.do_backward else "CLEAN_SHORT"
                    self._started_op = False
                    return {'RUNNING_MODAL'}
                self._fwd_done = True
                return {'RUNNING_MODAL'}

            if self._state == "TRACK_BWD":
                if not self._started_op:
                    try:
                        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
                        self.report({'INFO'}, "[TRACK_BWD] started (INVOKE_DEFAULT)")
                        self._started_op = True
                        return {'RUNNING_MODAL'}
                    except Exception as ex:
                        self.report({'WARNING'}, f"[TRACK_BWD] start failed: {ex}")
                        self._bwd_done = True
                if self._bwd_done:
                    self._state = "CLEAN_SHORT"
                    self._started_op = False
                    return {'RUNNING_MODAL'}
                self._bwd_done = True
                return {'RUNNING_MODAL'}

            if self._state == "CLEAN_SHORT":
                if self.auto_clean_short and clean_short_tracks:
                    try:
                        clean_short_tracks(context, action='DELETE_TRACK')
                        self.report({'INFO'}, "[CLEAN_SHORT] short tracks removed")
                    except Exception as ex:
                        self.report({'WARNING'}, f"[CLEAN_SHORT] failed: {ex}")
                self._state = "FIND_LOW"
                return {'RUNNING_MODAL'}

            if self._state == "SOLVE":
                if run_solve_watch_clean:
                    try:
                        ok = run_solve_watch_clean(context)
                        self.report({'INFO'}, f"[SOLVE] finished (ok={ok})")
                    except Exception as ex:
                        self.report({'WARNING'}, f"[SOLVE] failed: {ex}")
                self._state = "DONE"
                return {'RUNNING_MODAL'}

            if self._state == "DONE":
                self._deactivate_flag(context)
                return {'FINISHED'}

            self.report({'WARNING'}, f"Unknown state: {self._state}")
            self._deactivate_flag(context)
            self._state = "DONE"
            return {'CANCELLED'}

        except Exception as ex:
            self.report({'ERROR'}, f"Pipeline error in state {self._state}: {ex}")
            self._deactivate_flag(context)
            self._state = "DONE"
            return {'CANCELLED'}


classes = (CLIP_OT_tracking_coordinator,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
