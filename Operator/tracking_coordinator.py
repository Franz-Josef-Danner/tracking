from __future__ import annotations
import bpy

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Optimize)"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "CLIP_EDITOR"

    def invoke(self, context, event):
        # Import NACH vollständigem Paketinit (vermeidet Zirkularprobleme)
        from .. import optimize_pipeline_fn as opt  # falls Datei im Paket‑Root heißt: optimize_pipeline_fn.py
        # oder: from ..Helper import optimize_pipeline_fn as opt  # wenn du sie unter Helper/ ablegst
        opt.start_optimization(context)
        self.report({'INFO'}, "Optimization started (functional pipeline)")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
