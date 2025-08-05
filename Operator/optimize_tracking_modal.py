import bpy
from bpy.types import Operator
from bpy.props import IntProperty
from ..Helper.set_test_value import set_test_value
from ..Helper.error_value import error_value
from ..Helper.disable_proxy import CLIP_OT_disable_proxy
from ..Helper.enable_proxy import CLIP_OT_enable_proxy
from .detect import perform_marker_detection

class CLIP_OT_optimize_tracking_modal(Operator):
    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimiertes Tracking (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0
    _phase = 0
    _ev = -1
    _dg = 0
    _pt = 21
    _ptv = 21
    _sus = 42
    _mov = 0
    _vf = 0
    _clip = None

    def modal(self, context, event):
        if event.type == 'TIMER':
            try:
                return self.run_step(context)
            except Exception as e:
                self.report({'ERROR'}, f"Fehler: {str(e)}")
                return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def run_step(self, context):
        clip = self._clip
        def set_flag1(pattern, search):
            settings = clip.tracking.settings
            settings.default_pattern_size = max(5, min(1000, int(pattern)))
            settings.default_search_size = max(5, min(1000, int(search)))

        def set_flag2(index):
            motion_models = ['Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot', 'Loc']
            if 0 <= index < len(motion_models):
                clip.tracking.settings.default_motion_model = motion_models[index]

        def set_flag3(index):
            s = clip.tracking.settings
            s.use_default_red_channel = (index in [0, 1])
            s.use_default_green_channel = (index in [1, 2, 3])
            s.use_default_blue_channel = (index in [3, 4])

        def call_marker_helper():
            bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

        def set_marker():
            bpy.ops.clip.disable_proxy('EXEC_DEFAULT')
            call_marker_helper()
            w = clip.size[0]
            margin = int(w * 0.025)
            min_dist = int(w * 0.05)
            return perform_marker_detection(clip, clip.tracking, 0.75, margin, min_dist)

        def track():
            bpy.ops.clip.enable_proxy('EXEC_DEFAULT')
            for t in clip.tracking.tracks:
                if t.select:
                    clip.tracking.tracks.active = t
                    bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)

        def frames_per_track_all():
            return sum(len(t.markers) for t in clip.tracking.tracks if t.select)

        def measure_error_all():
            return error_value(clip)

        def eg(frames, error):
            return frames / error if error else 0

        if self._phase == 0:
            set_flag1(self._pt, self._sus)
            set_marker()
            track()
            f = frames_per_track_all()
            e = measure_error_all()
            g = eg(f, e)
            print(f"[Zyklus 1] f={f}, e={e:.4f}, g={g:.4f}")
            bpy.ops.clip.delete_track(confirm=False)

            if self._ev < 0:
                self._ev = g
                self._pt *= 1.1
                self._sus = self._pt * 2
            elif g > self._ev:
                self._ev = g
                self._dg = 4
                self._ptv = self._pt
                self._pt *= 1.1
                self._sus = self._pt * 2
            else:
                self._dg -= 1
                if self._dg >= 0:
                    self._pt *= 1.1
                    self._sus = self._pt * 2
                else:
                    self._pt = self._ptv
                    self._sus = self._pt * 2
                    self._phase = 1

        elif self._phase == 1:
            if self._step < 5:
                set_flag2(self._step)
                set_marker()
                track()
                f = frames_per_track_all()
                e = measure_error_all()
                g = eg(f, e)
                print(f"[Zyklus 2] Motion {self._step} → g={g:.4f}")
                if g > self._ev:
                    self._ev = g
                    self._mov = self._step
                bpy.ops.clip.delete_track(confirm=False)
                self._step += 1
            else:
                self._step = 0
                self._phase = 2

        elif self._phase == 2:
            if self._step < 5:
                set_flag3(self._step)
                set_marker()
                track()
                f = frames_per_track_all()
                e = measure_error_all()
                g = eg(f, e)
                print(f"[Zyklus 3] RGB {self._step} → g={g:.4f}")
                if g > self._ev:
                    self._ev = g
                    self._vf = self._step
                bpy.ops.clip.delete_track(confirm=False)
                self._step += 1
            else:
                set_flag2(self._mov)
                set_flag3(self._vf)
                self.report({'INFO'}, f"Fertig: ev={self._ev:.2f}, Motion={self._mov}, RGB={self._vf}")
                self.cancel(context)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        return {'FINISHED'}  # Not used

    def invoke(self, context, event):
        self._clip = context.space_data.clip
        if not self._clip:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        set_test_value(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
