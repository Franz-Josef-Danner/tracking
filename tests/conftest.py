import sys
import os
from types import ModuleType, SimpleNamespace

if 'bpy' not in sys.modules:
    bpy = ModuleType('bpy')
    bpy.__path__ = []
    bpy.ops = SimpleNamespace()
    bpy.ops.clip = SimpleNamespace()
    props = ModuleType('bpy.props')
    props.IntProperty = lambda *a, **k: None
    props.FloatProperty = lambda *a, **k: None
    props.BoolProperty = lambda *a, **k: None
    sys.modules['bpy'] = bpy
    sys.modules['bpy.props'] = props
    bpy.props = props
    bpy.types = SimpleNamespace(Operator=object, Panel=object)
    bpy.context = SimpleNamespace(scene=SimpleNamespace(), space_data=SimpleNamespace(), area=None)

os.environ.setdefault("BLENDER_TEST", "1")



print("conftest loaded")

