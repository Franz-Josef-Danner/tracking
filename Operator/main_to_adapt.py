import bpy

__all__ = ("CLIP_OT_launch_main_with_adapt",)

def _clip_override(context):
    for area in context.window.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None

class CLIP_OT_launch_main_with_adapt(bpy.types.Operator):
    """Berechnet marker_adapt aus marker_basis und startet anschließend clip.main mit Übergabe."""
    bl_idname = "clip.launch_main_with_adapt"
    bl_label  = "Start Main (Adapt x4)"
    bl_options = {'REGISTER'}

    factor: bpy.props.IntProperty(
        name="Faktor",
        description="Multiplikator für marker_basis → marker_adapt",
        default=4, min=1, max=999
    )

    use_override: bpy.props.BoolProperty(
        name="CLIP-Override",
        description="Operator im CLIP_EDITOR-Kontext ausführen",
        default=True
    )

    def execute(self, context):
        scene = context.scene
        marker_basis = int(scene.get("marker_basis", 25))
        marker_adapt = int(marker_basis * self.factor * 0,9)

        if self.use_override:
            ovr = _clip_override(context)
            if ovr:
                with context.temp_override(**ovr):
                    return bpy.ops.clip.main('INVOKE_DEFAULT', marker_adapt=marker_adapt)

        # Fallback ohne Override
        return bpy.ops.clip.main('INVOKE_DEFAULT', marker_adapt=marker_adapt)
