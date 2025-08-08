# Operator/tracking_pipeline.py
import bpy, time
from ..Helper.ram_helper import RamGuard

class CLIP_OT_tracking_pipeline(bpy.types.Operator):
    """Tracking-Pipeline: Detect, Track, Cleanup"""
    bl_idname = "clip.tracking_pipeline"
    bl_label = "Tracking Pipeline"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0
    _is_tracking = False
    _ram_guard = None

    def execute(self, context):
        # RAM-Guard initialisieren
        self._ram_guard = RamGuard(threshold_up=90.0, threshold_down=80.0, cooldown=5.0)

        scene = context.scene
        scene["pipeline_status"] = ""
        scene["detect_status"] = ""
        scene["bidirectional_status"] = ""

        self._step = 0
        self._is_tracking = True

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)

        scene["pipeline_status"] = "running"
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.report({'WARNING'}, "Tracking-Pipeline manuell abgebrochen.")
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            # RAM prüfen
            if self._ram_guard:
                event_name, _pct = self._ram_guard.poll()
                if event_name == 'enter_hot':
                    try:
                        bpy.ops.clip.enable_proxy(); bpy.ops.clip.reload()
                    except Exception:
                        pass
                elif event_name == 'leave_hot':
                    try:
                        bpy.ops.clip.disable_proxy(); bpy.ops.clip.reload()
                    except Exception:
                        pass

            # immer hier weiter
            return self.run_step(context)

        return {'PASS_THROUGH'}

    # --- helper: Clip-Editor-Kontext suchen
    def _find_clip_context(self, context):
        clip_area = clip_region = clip_space = None
        for a in context.screen.areas:
            if a.type == 'CLIP_EDITOR':
                for r in a.regions:
                    if r.type == 'WINDOW':
                        clip_area = a
                        clip_region = r
                        clip_space = a.spaces.active
                        return clip_area, clip_region, clip_space
        return None, None, None

    def run_step(self, context):
        scene = context.scene
        wm = context.window_manager

        # gültigen CLIP_EDITOR-Kontext beschaffen
        clip_area, clip_region, clip_space = self._find_clip_context(context)
        if not clip_space or not getattr(clip_space, "clip", None):
            self.report({'ERROR'}, "Kein Clip-Editor mit aktivem Clip gefunden.")
            self.cancel(context)
            return {'CANCELLED'}

        clip = clip_space.clip
        ts = clip.tracking.settings
        ts.default_margin = ts.default_search_size

        if self._step == 0:
            bpy.ops.clip.marker_helper_main()
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            # (früher Proxy-Step) – bewusst leer
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 2:
            bpy.ops.clip.detect()
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 3:
            detect_status = scene.get("detect_status", "")
            if detect_status == "success":
                self._step += 1
                scene["detect_status"] = ""
                return {'PASS_THROUGH'}
            elif detect_status == "failed":
                self.report({'ERROR'}, "❌ Detect fehlgeschlagen – Pipeline wird abgebrochen.")
                self.cancel(context)
                return {'CANCELLED'}
            return {'PASS_THROUGH'}

        elif self._step == 4:
            ts = clip.tracking.settings
            ts.default_margin = ts.default_search_size
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 5:
            bpy.ops.clip.bidirectional_track()
            self._step += 1
            return {'PASS_THROUGH'}

        elif self._step == 6:
            if scene.get("bidirectional_status", "") == "done":
                scene["bidirectional_status"] = ""
                self._is_tracking = False

            if not self._is_tracking:
                # 👉 genau hier EINMAL den Error-Cleanup im gültigen Clip-Kontext aufrufen
                with context.temp_override(area=clip_area, region=clip_region, space_data=clip_space):
                    # verbose=True nur wenn du Konsolen-Ausgaben willst
                    bpy.ops.clip.clean_error_tracks('EXEC_DEFAULT', verbose=True)

                scene["pipeline_status"] = "done"
                wm.event_timer_remove(self._timer)
                return {'FINISHED'}

            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        scene = context.scene
        scene["pipeline_status"] = ""
        scene["detect_status"] = ""
        scene["bidirectional_status"] = ""
        scene["goto_frame"] = -1
        if "repeat_frame" in scene:
            scene["repeat_frame"].clear()
