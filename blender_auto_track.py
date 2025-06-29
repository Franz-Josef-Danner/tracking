bl_info = {
    "name": "Auto Track Tools",
    "blender": (2, 80, 0),
    "category": "Clip",
    "author": "Auto Generated",
    "version": (1, 2, 1),
    "description": (
        "Provide an Auto Track panel with configurable tracking settings"
    ),
}

import bpy


class AutoTrackProperties(bpy.types.PropertyGroup):
    """Properties stored in the scene for auto tracking"""

    min_marker_count: bpy.props.IntProperty(
        name="Minimum Marker Count",
        description="Minimum number of markers required before tracking",
        default=10,
        min=0,
    )

    min_tracking_length: bpy.props.IntProperty(
        name="Minimum Tracking Length",
        description="Minimum length of a track in frames",
        default=10,
        min=0,
    )

    @property
    def min_marker_multiplier(self):
        """Four times the minimum marker count"""
        return self.min_marker_count * 4

    @property
    def min_marker_count_plus_small(self):
        """Minimum marker count increased by 80 percent"""
        return int(self.min_marker_count * 0.8)

    @property
    def min_marker_count_plus_big(self):
        """Minimum marker count increased by 120 percent"""
        return int(self.min_marker_count * 1.2)


class CLIP_OT_auto_track_settings(bpy.types.Operator):
    """Show the auto track sidebar in the Clip Editor"""

    bl_idname = "clip.auto_track_settings"
    bl_label = "Auto Track Settings"

    def execute(self, context):
        area = context.area
        if area.type == 'CLIP_EDITOR':
            area.spaces.active.show_region_ui = True
            self.report({'INFO'}, "Auto Track settings opened")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Clip Editor not active")
            return {'CANCELLED'}


class CLIP_OT_auto_track_start(bpy.types.Operator):
    """Set Motion Model to LocRotScale for UI and active track"""

    bl_idname = "clip.auto_track_start"
    bl_label = "Auto Track Start"

    def execute(self, context):
        try:
            space = context.space_data
            if not (space and space.clip):
                self.report({'ERROR'}, "No movie clip found")
                return {'CANCELLED'}

            # Set global UI motion model
            tracking = space.clip.tracking
            settings = tracking.settings

            # Blender versions may expose the motion model setting under
            # different names; try both possibilities to remain compatible
            if hasattr(settings, "motion_model"):
                settings.motion_model = 'LocRotScale'
            elif hasattr(settings, "default_motion_model"):
                settings.default_motion_model = 'LocRotScale'
            else:
                self.report({'WARNING'}, "Motion model property not found")

            # Optional: Set motion model for active track
            track = tracking.tracks.active
            if track:
                track.motion_model = 'LocRotScale'
            else:
                self.report({'WARNING'}, "No active track selected")

            # Force UI refresh
            for area in context.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()

            self.report({'INFO'}, "Motion model set to LocRotScale")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class CLIP_PT_auto_track_settings_panel(bpy.types.Panel):
    """Panel in the Clip Editor sidebar displaying auto track options"""

    bl_label = "Auto Track Settings"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Auto Track'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.auto_track_settings

        layout.prop(settings, "min_marker_count")
        layout.prop(settings, "min_tracking_length")
        layout.separator()
        layout.operator(
            CLIP_OT_auto_track_start.bl_idname,
            text="Auto Track Start",
        )


classes = (
    AutoTrackProperties,
    CLIP_OT_auto_track_settings,
    CLIP_OT_auto_track_start,
    CLIP_PT_auto_track_settings_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.auto_track_settings = bpy.props.PointerProperty(
        type=AutoTrackProperties
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.auto_track_settings


if __name__ == "__main__":
    register()
