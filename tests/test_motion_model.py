import importlib
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Provide dummy bpy module
sys.modules.setdefault('bpy', SimpleNamespace())

motion_model = importlib.import_module("modules.tracking.motion_model")


class DummySettings:
    def __init__(self):
        self.motion_model = None


def test_next_model_cycles():
    motion_model._index = -1  # reset
    settings = DummySettings()
    first = motion_model.next_model(settings)
    second = motion_model.next_model(settings)
    third = motion_model.next_model(settings)
    # Should cycle through the list
    assert first == 'Perspective'
    assert second == 'Affine'
    assert third == 'LocRotScale'
    # settings attribute updated
    assert settings.motion_model == third

