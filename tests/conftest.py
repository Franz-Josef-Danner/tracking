import sys
from types import SimpleNamespace

# Provide dummy bpy and mathutils modules so addon can be imported during tests
dummy_bpy = sys.modules.setdefault("bpy", SimpleNamespace())
dummy_bpy.types = SimpleNamespace(Operator=object, Panel=object)
dummy_bpy.ops = SimpleNamespace(
    clip=SimpleNamespace(detect_features=lambda *a, **k: None)
)
dummy_bpy.props = SimpleNamespace(
    FloatProperty=lambda *a, **k: None,
    IntProperty=lambda *a, **k: None,
    BoolProperty=lambda *a, **k: None,
    EnumProperty=lambda *a, **k: None,
)
sys.modules.setdefault("bpy.ops", dummy_bpy.ops)
sys.modules.setdefault("bpy.props", dummy_bpy.props)
mathutils = SimpleNamespace(Vector=lambda *a, **k: None)
sys.modules.setdefault("mathutils", mathutils)
