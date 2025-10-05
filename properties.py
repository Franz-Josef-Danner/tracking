import bpy
from bpy.types import PropertyGroup
from bpy.props import IntProperty, FloatProperty, PointerProperty


class KTParameters(PropertyGroup):
    marker_per_frame: IntProperty(name="Marker per Frame", default=25, min=1, soft_max=200)

    # Berechnete Werte (read-only Anzeige im Panel)
    hz: IntProperty(name="hz", default=0)
    vc: IntProperty(name="vc", default=0)
    pz: IntProperty(name="pz", default=0)
    sz: IntProperty(name="sz", default=0)
    og: IntProperty(name="og", default=0)
    ug: IntProperty(name="ug", default=0)
    md: FloatProperty(name="md", default=0.0, precision=2)
    ma: FloatProperty(name="ma", default=0.0, precision=2)
    za: FloatProperty(name="za", default=0.0, precision=3)
    tr: IntProperty(name="tr", default=0)
    marker_count: IntProperty(name="Marker Count", default=0)


classes = (KTParameters,)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.kt_params = PointerProperty(type=KTParameters)


def unregister():
    if hasattr(bpy.types.Scene, 'kt_params'):
        delattr(bpy.types.Scene, 'kt_params')
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
