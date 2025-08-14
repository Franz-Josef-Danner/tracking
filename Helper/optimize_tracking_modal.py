import bpy
from bpy.types
from .set_test_value import set_test_value
from .error_value import error_value
# Proxy-Helper entfernt:
# from ..Helper.disable_proxy import CLIP_OT_disable_proxy
# from ..Helper.enable_proxy import CLIP_OT_enable_proxy
from .detect import perform_marker_detection, run_detect_adaptive, run_detect_once

    def execute(self, context):
        self._clip = context.space_data.clip
        if not self._clip:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        set_test_value(context)
        self._start_frame = context.scene.frame_current

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.report({'WARNING'}, "Tracking-Optimierung manuell abgebrochen.")
            self.cancel(context)
            return {'CANCELLED'}
    
        if event.type == 'TIMER':
            return self.run_step(context)
    
        return {'PASS_THROUGH'}

    def run_step(self, context):
        clip = self._clip

        def set_flag1(pattern, search):
            settings = clip.tracking.settings
            settings.default_pattern_size = int(pattern)
            settings.default_search_size = int(search)
            settings.default_margin = settings.default_search_size

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
