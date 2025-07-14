"""Utilities for switching tracking motion models."""

import bpy

_motion_models = ['Perspective', 'Affine', 'LocRotScale']
_index = 0


def next_model(settings=None):
    """Cycle through motion models on the tracking settings."""
    global _index
    _index = (_index + 1) % len(_motion_models)
    model = _motion_models[_index]
    if settings and hasattr(settings, 'motion_model'):
        settings.motion_model = model
    return model

