
import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame

class CLIP_OT_main(bpy.types.Operator):
    bl_idname = "clip.main"
    bl_label = "Main Setup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip

        if clip is None or not clip.tracking:
            self.report({'WARNING'}, "Kein gültiger Clip oder Tracking-Daten vorhanden.")
            return {'CANCELLED'}

        print("🚀 Starte Tracking-Pipeline...")
        bpy.ops.clip.tracking_pipeline()

        print("⏳ Warte auf Abschluss der Pipeline (Tracking Stabilität)...")
        timeout = 300  # max 60 Sekunden (0.2s * 300)
        counter = 0
        while scene.get("pipeline_status", "") != "done":
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            time.sleep(0.2)
            counter += 1
            if counter > timeout:
                self.report({'ERROR'}, "Tracking-Pipeline hat sich aufgehängt oder ist unvollständig.")
                return {'CANCELLED'}

        print("🧪 Starte Markerprüfung…")
        frame = find_low_marker_frame(clip)
        if frame is not None:
            print(f"🟡 Zu wenige Marker im Frame {frame}")
            scene["goto_frame"] = frame
            jump_to_frame(context)
        else:
            print("✅ Alle Frames haben ausreichend Marker.")

        self.report({'INFO'}, "Tracking vollständig abgeschlossen – inklusive Markerprüfung.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_main)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_main)

if __name__ == "__main__":
    register()
