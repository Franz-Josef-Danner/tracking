from .pattern_base import pattern_base
from .clamp_pattern_size import clamp_pattern_size
from .utils import MOTION_MODELS


def cycle_motion_model(settings, clip, reset_size=True):
    """Cycle to the next default motion model."""
    current = settings.default_motion_model
    try:
        index = MOTION_MODELS.index(current)
    except ValueError:
        index = -1
    next_model = MOTION_MODELS[(index + 1) % len(MOTION_MODELS)]
    settings.default_motion_model = next_model
    if reset_size:
        base = pattern_base(clip)
        settings.default_pattern_size = clamp_pattern_size(base, clip)
        settings.default_search_size = settings.default_pattern_size * 2
