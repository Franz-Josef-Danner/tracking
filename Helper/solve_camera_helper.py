import bpy

def _find_clip_context(context):
    for area in context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None

class CLIP_OT_solve_camera_helper(bpy.types.Operator):
    bl_idname = "clip.solve_camera_helper"
    bl_label = "Solve Camera (Context-Safe)"

    use_keyframe: bpy.props.BoolProperty(default=False)
    keyframe1: bpy.props.IntProperty(default=1, min=1)
    keyframe2: bpy.props.IntProperty(default=30, min=1)
    refine: bpy.props.EnumProperty(
        name="Refine",
        items=[
            ('FOCAL_LENGTH', "Focal", ""),
            ('FOCAL_LENGTH_RADIAL_K1', "Focal+K1", ""),
            ('FOCAL_LENGTH_RADIAL_K1_K2', "Focal+K1+K2", ""),
            ('FOCAL_LENGTH_RADIAL_K1_K2_PRINCIPAL_POINT', "Focal+K1+K2+PP", ""),
        ],
        default='FOCAL_LENGTH_RADIAL_K1_K2_PRINCIPAL_POINT',
    )

    def execute(self, context):
        area, region, space = _find_clip_context(context)
        if not area or not region or not space or not space.clip:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext.")
            return {'CANCELLED'}

        override = {
            "window": context.window,
            "screen": context.window.screen,
            "area": area,
            "region": region,
            "space_data": space,
        }
        try:
            # Kontext sicher über temp_override setzen
            with bpy.context.temp_override(
                window=context.window,
                screen=context.window.screen,
                area=area,
                region=region,
                space_data=space,
            ):
                bpy.ops.clip.solve_camera('INVOKE_DEFAULT',
                                          use_keyframe=self.use_keyframe,
                                          keyframe1=self.keyframe1,
                                          keyframe2=self.keyframe2,
                                          refine=self.refine)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Camera Solve fehlgeschlagen: {e}")
            return {'CANCELLED'}

