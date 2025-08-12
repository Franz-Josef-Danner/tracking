import bpy

__all__ = ("CLIP_OT_activate_main_with_adapt", "activate_main_with_adapt")

def _clip_override(context):
    for area in context.window.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None

def activate_main_with_adapt(context):
    scene = context.scene
    basis = int(scene.get("marker_basis", 25))
    adapt = int(basis * 4)

    # Nur den Ableitungswert persistieren; min/max werden weiterhin in main berechnet
    scene["marker_adapt"] = adapt

    ovr = _clip_override(context)
    if ovr:
        with context.temp_override(**ovr):
            return bpy.ops.clip.main('INVOKE_DEFAULT')
    return bpy.ops.clip.main('INVOKE_DEFAULT')

class CLIP_OT_activate_main_with_adapt(bpy.types.Operator):
    """Setzt marker_adapt = marker_basis * 4 und startet anschließend main."""
    bl_idname = "clip.activate_main_with_adapt"
    bl_label = "Activate Main (with Adapt)"

    def execute(self, context):
        result = activate_main_with_adapt(context)
        if result in {'FINISHED', 'RUNNING_MODAL', 'PASS_THROUGH'}:
            self.report({'INFO'}, "Main mit marker_adapt gestartet.")
            return {'RUNNING_MODAL'} if result == {'RUNNING_MODAL'} else {'FINISHED'}
        self.report({'WARNING'}, "Main konnte nicht gestartet werden.")
        return {'CANCELLED'}
