import bpy
from bpy.types import Operator

class CLIP_OT_marker_adapt_boost(Operator):
    """Erhöht scene['marker_adapt'] um +10% und speichert den neuen Wert."""
    bl_idname = "clip.marker_adapt_boost"
    bl_label = "Marker Adapt +10%"
    bl_options = {"INTERNAL", "REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene

        # Ausgangswert ermitteln (Fallback: marker_basis → 25)
        base = scene.get("marker_adapt", None)
        if base is None:
            base = scene.get("marker_basis", 25)

        try:
            base_val = float(base)
        except Exception:
            base_val = 25.0

        new_val = round(base_val * 1.1)
        scene["marker_adapt"] = int(new_val)

        self.report({'INFO'}, f"marker_adapt angehoben: {int(base_val)} → {int(new_val)}")
        print(f"[MarkerAdapt] marker_adapt: {int(base_val)} → {int(new_val)}")
        return {'FINISHED'}


__all__ = ("CLIP_OT_marker_adapt_boost",)

classes = (CLIP_OT_marker_adapt_boost,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
