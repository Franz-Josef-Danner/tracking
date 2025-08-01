"""Combined operator to set dynamic default tracking settings."""

import bpy


class TRACK_OT_test_combined(bpy.types.Operator):
    """Apply dynamic default tracking settings"""

    bl_idname = "track.test_combined"
    bl_label = "Test Default"
    bl_description = "Setzt dynamische Default-Tracking-Parameter"

    @classmethod
    def poll(cls, context):
        return (
            context.space_data is not None
            and getattr(context.space_data, "clip", None) is not None
        )

    def execute(self, context):
        clip = context.space_data.clip
        settings = clip.tracking.settings

        width = clip.size[0]

        pattern_size = int(width / 500)
        search_size = pattern_size * 2

        settings.default_pattern_size = pattern_size
        settings.default_search_size = search_size
        settings.default_motion_model = "Loc"
        settings.default_pattern_match = "KEYFRAME"
        settings.use_default_brute = True
        settings.use_default_normalization = True
        settings.use_default_red_channel = True
        settings.use_default_green_channel = True
        settings.use_default_blue_channel = True
        settings.default_weight = 1.0
        settings.default_correlation_min = 0.9
        settings.default_margin = 10

        self.report(
            {"INFO"},
            f"Tracking-Defaults gesetzt (Pattern: {pattern_size}, Search: {search_size})",
        )
        return {"FINISHED"}


classes = (TRACK_OT_test_combined,)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
