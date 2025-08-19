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
        # Richtiges Modul laden: Helper/optimize_tracking_modal.py
        from ..Helper import optimize_tracking_modal as opt
        opt.start_optimization(context)
        self.report({'INFO'}, "Optimization started (functional pipeline)")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
