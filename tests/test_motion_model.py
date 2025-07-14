import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from types import SimpleNamespace

# Provide dummy bpy module
sys.modules.setdefault('bpy', SimpleNamespace())

from modules.tracking import motion_model


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

