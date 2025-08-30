
 __all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")
 

class CLIP_OT_tracking_bootstrap_only(bpy.types.Operator):
    """Kaiserlich: Nur Bootstrap ausführen (kein Timer/Orchestrator)"""
    bl_idname = "clip.tracking_bootstrap_only"
    bl_label = "Kaiserlich: Bootstrap Only"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context and getattr(context, "scene", None))

    def execute(self, context):
        try:
            bootstrap(context)
            self.report({'INFO'}, "Bootstrap ausgeführt")
            print("[BootstrapOnly] Bootstrap erfolgreich ausgeführt")
        except Exception as ex:
            self.report({'ERROR'}, f"Bootstrap fehlgeschlagen: {ex}")
            print(f"[BootstrapOnly] FAILED → {ex}")
            return {'CANCELLED'}
        return {'FINISHED'}


 # ------------------------------------------------------------
 # Utility: Track-/Marker-Handling (Selektieren/Löschen)
 # ------------------------------------------------------------
@@
 def register():
     bpy.utils.register_class(CLIP_OT_tracking_coordinator)
    bpy.utils.register_class(CLIP_OT_tracking_bootstrap_only)
 
 def unregister():
     print(f"[Coordinator] unregister() from {__file__}")
     try:
         bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
     except Exception:
         pass
    try:
        bpy.utils.unregister_class(CLIP_OT_tracking_bootstrap_only)
    except Exception:
        pass
