import bpy

class CLIP_OT_tracking_pipeline(bpy.types.Operator):
    bl_idname = "clip.tracking_pipeline"
    bl_label = "Tracking Pipeline"
    bl_description = "Führt Marker-Hilfe, Tracking, Proxy-Steuerung und Cleanup aus"

    def execute(self, context):
        scene = context.scene

        clip = context.space_data.clip
        if not clip:
            self.report({'ERROR'}, "Kein Movie Clip aktiv")
            return {'CANCELLED'}

        # 1. Marker Helper
        bpy.ops.clip.marker_helper_main()

        # 2. Proxy deaktivieren
        bpy.ops.clip.disable_proxy()

        # 3. Detect
        bpy.ops.clip.detect()

        # 4. Proxy aktivieren
        bpy.ops.clipenable_proxy()

        # 5. Bidirektionales Tracking
        bpy.ops.clip.bidirectional_track()

        # 6. Clean Short Tracks
        bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')

        self.report({'INFO'}, "Tracking-Pipeline abgeschlossen")
        return {'FINISHED'}
