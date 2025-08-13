import bpy

__all__ = (
    "CLIP_OT_main_to_adapt",
)

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


class CLIP_OT_main_to_adapt(bpy.types.Operator):
    """
    1) Leitet marker_adapt aus scene['marker_basis'] * factor * 0.9 ab und speichert ihn in scene['marker_adapt'].
    2) Startet anschließend die Kette mit clip.tracker_settings (die danach clip.find_low_marker triggert).
    """
    bl_idname = "clip.main_to_adapt"
    bl_label  = "main_to_adapt (Adapt xF)"
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
        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        marker_basis = int(scene.get("marker_basis", 25))
        marker_adapt = int(marker_basis * self.factor * 0.9)

        # Szenenvariable persistieren → wird downstream konsumiert
        scene["marker_adapt"] = marker_adapt
        print(f"[MainToAdapt] marker_adapt gesetzt: {marker_adapt} (basis={marker_basis}, factor={self.factor})")

        # Nächster Schritt der Kette: tracker_settings (ruft danach find_low_marker)
        try:
            ovr = _clip_override(context) if self.use_override else None
            if ovr:
#                with context.temp_override(**ovr):
#                    res = bpy.ops.clip.tracker_settings('INVOKE_DEFAULT')
            else:
#                res = bpy.ops.clip.tracker_settings('INVOKE_DEFAULT')

                print(f"[MainToAdapt] Übergabe an tracker_settings → {res}")
                return {'FINISHED'}
#        except Exception as e:
#            self.report({'ERROR'}, f"tracker_settings konnte nicht gestartet werden: {e}")
#            return {'CANCELLED'}


# Registration
classes = (CLIP_OT_main_to_adapt,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
