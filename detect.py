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
        min_new = context.scene.detect_min_features
        tracks_before = len(clip.tracking.tracks)

        print(
            f"[Detect] Running detection for {min_new} markers at "
            f"threshold {threshold:.4f}"
        )
        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=500,
            min_distance=10,
            placement='FRAME',
        )

        tracks_after = len(clip.tracking.tracks)

        while (tracks_after - tracks_before) < min_new and threshold > 0.0001:
            threshold *= 0.9
            msg = (
                f"Nur {tracks_after - tracks_before} Features, "
                f"senke Threshold auf {threshold:.4f}"
            )
            print(f"[Detect] {msg}")
            self.report({'INFO'}, msg)
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=500,
                min_distance=10,
                placement='FRAME',
            )
            tracks_after = len(clip.tracking.tracks)
        print(
            f"[Detect] Finished with {tracks_after - tracks_before} new markers"
        )
        return {'FINISHED'}

# Panel-Klasse
class CLIP_PT_DetectFeaturesPanel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Motion Tracking'
    bl_label = "Detect Features Tool"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "detect_min_features")
        layout.operator("clip.detect_features_custom", icon='VIEWZOOM')

# Registrierung
def register():
    bpy.types.Scene.detect_min_features = bpy.props.IntProperty(
        name="Min New Markers",
        default=1,
        min=1,
        description="Minimum markers to detect each run",
    )

    bpy.utils.register_class(DetectFeaturesCustomOperator)
    bpy.utils.register_class(CLIP_PT_DetectFeaturesPanel)

def unregister():
    bpy.utils.unregister_class(DetectFeaturesCustomOperator)
    bpy.utils.unregister_class(CLIP_PT_DetectFeaturesPanel)

    del bpy.types.Scene.detect_min_features

if __name__ == "__main__":
    register()
