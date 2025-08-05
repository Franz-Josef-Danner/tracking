import bpy
from bpy.types import Operator

class CLIP_OT_tracking_pipeline(Operator):
    """Modulare Tracking Pipeline mit Abschlussüberwachung"""
    bl_idname = "clip.tracking_pipeline"
    bl_label = "Tracking Pipeline"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0
    _is_tracking = False

    def execute(self, context):
        print("🚀 Starte Tracking-Pipeline...")
        self._step = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        return self.run_step(context)

    def run_step(self, context):
        wm = context.window_manager

        if self._step == 0:
            print("→ Marker Helper")
            bpy.ops.clip.marker_helper_main()
            self._step += 1

        elif self._step == 1:
            print("→ Proxy deaktivieren")
            bpy.ops.clip.disable_proxy()
            self._step += 1

        elif self._step == 2:
            print("→ Detect")
            bpy.ops.clip.detect()
            self._step += 1

        elif self._step == 3:
            print("→ Proxy aktivieren")
            bpy.ops.clip.enable_proxy()
            self._step += 1

        elif self._step == 4:
            print("→ Starte bidirektionales Tracking")
            bpy.ops.clip.bidirectional_track()
            self._is_tracking = True
            self._step += 1

        elif self._step == 5:
            # Warten bis bidirectional_track abgeschlossen ist
            if not self._is_tracking:
                print("→ Starte Clean Short Tracks")
                bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')
                wm.event_timer_remove(self._timer)
                print("✓ Pipeline abgeschlossen.")
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
