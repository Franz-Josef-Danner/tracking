import bpy

class TRACK_OT_test_combined(bpy.types.Operator):
    """Setzt die Default-Tracking-Einstellungen direkt."""
    bl_idname = "track.test_combined"
    bl_label = "Test Default"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'CLIP_EDITOR'

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Movie Clip gefunden")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        width = clip.size[0]

        pattern_size = int(width / 500)
        search_size = pattern_size * 2

        settings.default_pattern_size = pattern_size
        settings.default_search_size = search_size
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

        self.report({'INFO'}, f"Tracking-Defaults gesetzt (Pattern: {pattern_size}, Search: {search_size})")
        return {'FINISHED'}


# Registrierung (optional, falls nicht zentral erledigt)
def register():
    bpy.utils.register_class(TRACK_OT_test_combined)

def unregister():
    bpy.utils.unregister_class(TRACK_OT_test_combined)
