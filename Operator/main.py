
import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame

class CLIP_OT_main(bpy.types.Operator):
    bl_idname = "clip.main"
    bl_label = "Main Setup (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _step = 0

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip

        if clip is None or not clip.tracking:
            self.report({'WARNING'}, "Kein gültiger Clip oder Tracking-Daten vorhanden.")
            return {'CANCELLED'}

        print("🚀 Starte Tracking-Pipeline...")
        bpy.ops.clip.tracking_pipeline()
        print("⏳ Warte auf Abschluss der Pipeline...")

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self._step = 0

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene

        if self._step == 0:
            if scene.get("pipeline_status", "") == "done":
                print("🧪 Starte Markerprüfung…")
                self._step = 1  # Weiter zu Markerprüfung
            return {'PASS_THROUGH'}

        elif self._step == 1:
            clip = context.space_data.clip
            frame = find_low_marker_frame(clip)
            if frame is not None:
                print(f"🟡 Zu wenige Marker im Frame {frame}")
                scene["goto_frame"] = frame
                jump_to_frame(context)
            else:
                print("✅ Alle Frames haben ausreichend Marker.")

            self._step = 2  # Abschluss
            return {'PASS_THROUGH'}

        elif self._step == 2:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self.report({'INFO'}, "Tracking + Markerprüfung abgeschlossen.")
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

def register():
    bpy.utils.register_class(CLIP_OT_main)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_main)

if __name__ == "__main__":
    register()
