import bpy
from ..Helper.marker_helper_main import run_marker_helper
from ..Helper.disable_proxy import disable_proxy
from ..Helper.enable_proxy import enable_proxy

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
        marker_helper(clip)

        # 2. Proxy deaktivieren
        disable_proxy(clip)

        # 3. Detect
        bpy.ops.clip.detect()

        # 4. Proxy aktivieren
        enable_proxy(clip)

        # 5. Bidirektionales Tracking
        bpy.ops.clip.bidirectional_track()

        # 6. Clean Short Tracks
        bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')

        self.report({'INFO'}, "Tracking-Pipeline abgeschlossen")
        return {'FINISHED'}
