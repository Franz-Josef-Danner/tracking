import bpy
from ..Helper.bootstrap import run_bootstrap

class KAISERLICHTRACKER_OT_detect_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.detect_cycle"
    bl_label = "Detect Cyclus"
    bl_description = "Berechnet Parameter (Pattern/Search) basierend auf Auflösung und Eingabe"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_markers_per_frame
        run_bootstrap(context, ef)
        self.report({'INFO'}, "Bootstrap abgeschlossen – Werte in Console")
        return {'FINISHED'}
