import bpy

class KAISERLICH_PT_tracker(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich Tracker'
    bl_label = 'Kaiserlich Tracker'

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        props = scn.kaiserlich_tracker
        layout.prop(props, 'marker_per_frame')
        layout.operator('kaiserlich.detect_cyclus', icon='TRACKING')

class KaiserlichTrackerProperties(bpy.types.PropertyGroup):
    # Direkt in der Klasse definieren (notwendig für Blender RNA Registrierung)
    marker_per_frame: bpy.props.IntProperty(
        name='Marker per Frame',
        description='Anzahl Marker pro Frame',
        default=25,
        min=1
    )


classes = (
    KaiserlichTrackerProperties,
    KAISERLICH_PT_tracker,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.kaiserlich_tracker = bpy.props.PointerProperty(type=KaiserlichTrackerProperties)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.kaiserlich_tracker
