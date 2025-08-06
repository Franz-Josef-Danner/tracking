import bpy
from ..Helper.find_low_marker_frame import get_first_low_marker_frame
import time

class CLIP_OT_main(bpy.types.Operator):
    """Main Tracking Setup inklusive automatischem Tracking-Zyklus"""
    bl_idname = "clip.main"
    bl_label = "Main Setup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip

        if clip is None or not clip.tracking:
            self.report({'WARNING'}, "Kein gültiger Clip oder Tracking-Daten vorhanden.")
            return {'CANCELLED'}

        # Tracking-Zyklus
        while True:
            start_frame = scene.frame_current
            result = bpy.ops.clip.tracking_pipeline()

            # Warte bis Pipeline fertig ist
            print("⏳ Warte auf Abschluss der Pipeline...")
            while True:
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                time.sleep(0.2)
                if scene.frame_current == start_frame:
                    break

            # Prüfe nach Abschluss der Pipeline auf schwache Markerframes
            frame = get_first_low_marker_frame(context)

            if frame is not None:
                self.report({'INFO'}, f"Neustart Zyklus – schlechter Frame gefunden: {frame}")
                context.scene.frame_current = frame
                continue  # Starte den Zyklus erneut
            else:
                self.report({'INFO'}, "Tracking abgeschlossen – keine fehlerhaften Frames mehr gefunden.")
                break

        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_main)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_main)
