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
        scene = context.scene

        if scene.get("tracking_pipeline_active", False):
            self.report({'WARNING'}, "Tracking-Pipeline läuft bereits.")
            return {'CANCELLED'}

        print("🚀 Starte Tracking-Pipeline...")
        scene["tracking_pipeline_active"] = True

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
        scene = context.scene

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
            scene["tracking_pipeline_active"] = False  # Temporär deaktivieren
            result = bpy.ops.clip.detect()
            scene["tracking_pipeline_active"] = True   # Wieder aktivieren

            if result != {'FINISHED'}:
                print("✖ Detect wurde abgebrochen oder schlug fehl.")
                wm.event_timer_remove(self._timer)
                scene["tracking_pipeline_active"] = False
                return {'CANCELLED'}

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
            if not self._is_tracking:
                print("→ Starte Clean Short Tracks")
                bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')
                wm.event_timer_remove(self._timer)
                scene["tracking_pipeline_active"] = False
                print("✓ Pipeline abgeschlossen.")
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        context.scene["tracking_pipeline_active"] = False


def register():
    bpy.utils.register_class(CLIP_OT_tracking_pipeline)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_pipeline)
