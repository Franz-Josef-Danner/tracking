import bpy

# Operator-Klasse
class DetectFeaturesCustomOperator(bpy.types.Operator):
    bl_idname = "clip.detect_features_custom"
    bl_label = "Detect Features (Custom)"

    def execute(self, context):
        # ruft die Feature-Erkennung mit spezifischen Einstellungen auf
        bpy.ops.clip.detect_features(
            threshold=0.01,
            margin=500,
            min_distance=10,
            placement='FRAME'
        )
        return {'FINISHED'}

# Panel-Klasse
class CLIP_PT_DetectFeaturesPanel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Motion Tracking'
    bl_label = "Detect Features Tool"

    def draw(self, context):
        self.layout.operator("clip.detect_features_custom", icon='VIEWZOOM')

# Registrierung
def register():
    bpy.utils.register_class(DetectFeaturesCustomOperator)
    bpy.utils.register_class(CLIP_PT_DetectFeaturesPanel)

def unregister():
    bpy.utils.unregister_class(DetectFeaturesCustomOperator)
    bpy.utils.unregister_class(CLIP_PT_DetectFeaturesPanel)

if __name__ == "__main__":
    register()
