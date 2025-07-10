import bpy

# Operator-Klasse
class DetectFeaturesCustomOperator(bpy.types.Operator):
    bl_idname = "clip.detect_features_custom"
    bl_label = "Detect Features (Custom)"

    def execute(self, context):
        """Run feature detection and lower threshold if none are found."""

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        threshold = 0.01
        min_new = context.scene.min_marker_count
        tracks_before = len(clip.tracking.tracks)
        settings = clip.tracking.settings

        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=500,
            min_distance=10,
            placement='FRAME',
        )

        tracks_after = len(clip.tracking.tracks)
        if tracks_after == tracks_before:
            settings.default_pattern_size = max(
                1,
                int(settings.default_pattern_size / 1.1),
            )
            settings.default_search_size = settings.default_pattern_size * 2

        while (tracks_after - tracks_before) < min_new and threshold > 0.0001:
            if tracks_after == tracks_before:
                settings.default_pattern_size = max(
                    1,
                    int(settings.default_pattern_size / 1.1),
                )
                settings.default_search_size = settings.default_pattern_size * 2

            factor = ((tracks_after - tracks_before) + 0.1) / min_new
            threshold = max(threshold * factor, 0.0001)
            msg = (
                f"Nur {tracks_after - tracks_before} Features, "
                f"senke Threshold auf {threshold:.4f}"
            )
            self.report({'INFO'}, msg)
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=500,
                min_distance=10,
                placement='FRAME',
            )
            tracks_after = len(clip.tracking.tracks)
        return {'FINISHED'}

# Panel-Klasse
class CLIP_PT_DetectFeaturesPanel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Motion Tracking'
    bl_label = "Detect Features Tool"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "min_marker_count")
        layout.operator("clip.detect_features_custom", icon='VIEWZOOM')

classes = (
    DetectFeaturesCustomOperator,
    CLIP_PT_DetectFeaturesPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)



def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
