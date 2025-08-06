import bpy
from ..Helper.find_low_marker_frame import get_first_low_marker_frame

class CLIP_OT_main(bpy.types.Operator):
    """Main Tracking Setup inklusive automatischem Tracking-Zyklus"""
    bl_idname = "clip.main"
    bl_label = "Main Setup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Proxy deaktivieren
        bpy.ops.clip.disable_proxy()

        # Tracker Settings setzen
        bpy.ops.clip.tracker_settings()

        # Marker Setup ausführen
        bpy.ops.clip.marker_helper_main()

        # Starte den Tracking-Zyklus
        while True:
            result = bpy.ops.clip.tracking_pipeline()

            if result != {'FINISHED'}:
                self.report({'WARNING'}, "Tracking Pipeline konnte nicht abgeschlossen werden.")
                break

            frame = get_first_low_marker_frame(context)

            if frame is not None:
                self.report({'INFO'}, f"Neustart Zyklus – schlechter Frame gefunden: {frame}")
                context.scene.frame_current = frame
                continue  # Starte den Zyklus erneut
            else:
                self.report({'INFO'}, "Tracking abgeschlossen – keine fehlerhaften Frames mehr gefunden.")
                break

        return {'FINISHED'}
