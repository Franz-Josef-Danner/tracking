import bpy
import time

class CLIP_OT_tracking_pipeline(bpy.types.Operator):
    """Tracking-Pipeline: Detect, Track, Cleanup"""
    bl_idname = "clip.tracking_pipeline"
    bl_label = "Tracking Pipeline"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0
    _is_tracking = False

    def modal(self, context, event):
        if event.type == 'TIMER':
            return self.run_step(context)
        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._step = 0
        self._is_tracking = True
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        print("🚀 Starte Tracking-Pipeline...")
        context.scene["pipeline_status"] = "running"
        return {'RUNNING_MODAL'}

    def run_step(self, context):
        scene = context.scene

        # Rückmeldung vom Bidirectional Tracking
        if context.scene.get("bidirectional_status", "") == "done":
            self._is_tracking = False
            context.scene["bidirectional_status"] = ""  # Reset

        if self._step == 0:
            print("→ Marker Helper")
            bpy.ops.clip.marker_helper_main()
            self._step += 1

        elif self._step == 1:
            print("→ Proxy deaktivieren")
            bpy.ops.clip.proxy_disable()
            self._step += 1

        elif self._step == 2:
            print("→ Detect starten")
            bpy.ops.clip.detect()
            self._step += 1

        elif self._step == 3:
            print("⏳ Warte auf Detect-Abschluss...")
            if scene.get("detect_status", "") == "success":
                self._step += 1
                scene["detect_status"] = ""

        elif self._step == 4:
            print("→ Proxy aktivieren")
            bpy.ops.clip.proxy_enable()
            self._step += 1

        elif self._step == 5:
            print("→ Starte bidirektionales Tracking")
            bpy.ops.clip.bidirectional_track()
            self._step += 1

        elif self._step == 6:
            if not self._is_tracking:
                print("⏳ Warte auf Abschluss der Pipeline...")
                scene["pipeline_status"] = "done"
                wm = context.window_manager
                wm.event_timer_remove(self._timer)
                return {'FINISHED'}

        return {'PASS_THROUGH'}
