bl_info = {
    "name": "Tracking Tools",
    "author": "Addon Maintainer",
    "version": (1, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar > Addon",
    "description": "Minimal tracking addon with custom properties",
    "category": "Tracking",
}

import bpy


class TRACKING_OT_set_default_settings(bpy.types.Operator):
    """Set default tracking settings"""
    bl_idname = "tracking.set_default_settings"
    bl_label = "Default Settings"

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden")
            return {'CANCELLED'}
        settings = clip.tracking.settings
        settings.default_pattern_size = 10
        settings.default_search_size = 20
        settings.default_motion_model = 'Loc'
        settings.default_pattern_match = 'KEYFRAME'
        settings.use_default_brute = True
        settings.use_default_normalization = True
        settings.use_default_red_channel = True
        settings.use_default_green_channel = True
        settings.use_default_blue_channel = True
        settings.default_weight = 1.0
        settings.default_correlation_min = 0.9
        settings.default_margin = 10
        self.report({'INFO'}, "Tracking-Defaults gesetzt")
        return {'FINISHED'}

class TRACKING_PT_api_functions(bpy.types.Panel):
    bl_label = "API Funktionen"
    bl_idname = "TRACKING_PT_api_functions"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Addon"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Tracking-Vorgaben:")
        layout.prop(context.scene, "marker_basis")
        layout.prop(context.scene, "frames_per_track")

        layout.separator()
        layout.label(text="Initialisierung:")
        layout.operator("tracking.set_default_settings")
        layout.operator("tracking.marker_basis_values")


classes = (
    TRACKING_OT_set_default_settings,
    TRACKING_OT_marker_basis_values,
    TRACKING_PT_api_functions,
)


def register():
    if not hasattr(bpy.types.Scene, "marker_basis"):
        bpy.types.Scene.marker_basis = bpy.props.IntProperty(
            name="Marker/Frame",
            default=20,
            min=1,
            description="Zielanzahl von Markern pro Frame",
        )

    if not hasattr(bpy.types.Scene, "frames_per_track"):
        bpy.types.Scene.frames_per_track = bpy.props.IntProperty(
            name="Frames/Track",
            default=10,
            min=1,
            description="Minimale Länge eines gültigen Tracks",
        )

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    if hasattr(bpy.types.Scene, "marker_basis"):
        del bpy.types.Scene.marker_basis
    if hasattr(bpy.types.Scene, "frames_per_track"):
        del bpy.types.Scene.frames_per_track


if __name__ == "__main__":
    register()
