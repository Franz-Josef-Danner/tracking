
import bpy
import time
from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame

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

        print("🚀 Starte Tracking-Pipeline...")
        bpy.ops.clip.tracking_pipeline()

        print("⏳ Warte auf Abschluss der Pipeline (Tracking Stabilität)...")

        stable_count = 0
        prev_marker_count = len(clip.tracking.tracks)
        prev_frame = scene.frame_current

        while stable_count < 2:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            time.sleep(0.2)

            current_marker_count = len(clip.tracking.tracks)
            current_frame = scene.frame_current

            if current_marker_count == prev_marker_count and current_frame == prev_frame:
                stable_count += 1
            else:
                stable_count = 0
                prev_marker_count = current_marker_count
                prev_frame = current_frame

        # Erweiterung: Suche nach Frame mit zu wenigen Markern
        frame = find_low_marker_frame(clip)
        if frame is not None:
            scene["goto_frame"] = frame
            jump_to_frame(context)

        self.report({'INFO'}, "Tracking abgeschlossen – keine fehlerhaften Frames mehr gefunden.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_main)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_main)

if __name__ == "__main__":
    register()
