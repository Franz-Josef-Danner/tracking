import sys
from types import SimpleNamespace

# Provide dummy bpy and mathutils modules so addon can be imported during tests
dummy_bpy = sys.modules.setdefault("bpy", SimpleNamespace())
dummy_bpy.types = SimpleNamespace(Operator=object, Panel=object)
mathutils = SimpleNamespace(Vector=lambda *a, **k: None)
sys.modules.setdefault("mathutils", mathutils)
