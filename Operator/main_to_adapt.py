import bpy

__all__ = ("CLIP_OT_launch_find_low_marker_frame_with_adapt",)

def _clip_override(context):
    win = context.window
    if not win or not win.screen:
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None


class CLIP_OT_launch_find_low_marker_frame_with_adapt(bpy.types.Operator):
    """Berechnet marker_adapt aus marker_basis und startet anschließend clip.find_low_marker."""
    bl_idname = "clip.launch_find_low_marker_frame_with_adapt"
    bl_label  = "Start find_low_marker_frame (Adapt x4)"
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

    def invoke(self, context, event):
        # Delegiere sauber auf execute(), damit INVOKE_DEFAULT valide ist
        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        marker_basis = int(scene.get("marker_basis", 25))
        marker_adapt = int(marker_basis * self.factor * 0.9)

        # Szenenvariable persistieren → wird downstream (main/detect) konsumiert
        scene["marker_adapt"] = marker_adapt
        print(f"[MainToAdapt] marker_adapt in Scene gespeichert: {marker_adapt}")

        if self.use_override:
            ovr = _clip_override(context)
            if ovr:
                with context.temp_override(**ovr):
                    return bpy.ops.clip.find_low_marker('INVOKE_DEFAULT', use_scene_basis=True)

        # Fallback ohne Override – KORREKTER Operator-Name
        return bpy.ops.clip.find_low_marker('INVOKE_DEFAULT', use_scene_basis=True)


# Registrierung lokal möglich, Haupt-Register passiert in __init__.py
def register():
    bpy.utils.register_class(CLIP_OT_launch_find_low_marker_frame_with_adapt)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_launch_find_low_marker_frame_with_adapt)
