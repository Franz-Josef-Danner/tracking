"""Utility functions to cycle through Blender motion models.

This module defines the sequence of motion models used by the tracking cycle
and provides helpers to cycle to the next model or reset to the default.
"""

# Order matches the names from ``MovieTrackingSettings``
MOTION_MODEL_SEQUENCE = [
    "Loc",
    "LocRot",
    "LocScale",
    "LocRotScale",
    "Affine",
    "Perspective",
]

# Starting motion model
DEFAULT_MOTION_MODEL = "Loc"


def cycle_motion_model(settings):
    """Advance ``settings.default_motion_model`` to the next value."""

    current = settings.default_motion_model
    try:
        index = MOTION_MODEL_SEQUENCE.index(current)
    except ValueError:
        # Unknown value; do not change it to avoid breaking user setup
        return
    next_index = (index + 1) % len(MOTION_MODEL_SEQUENCE)
    settings.default_motion_model = MOTION_MODEL_SEQUENCE[next_index]


def reset_motion_model(settings):
    """Reset ``settings.default_motion_model`` to ``DEFAULT_MOTION_MODEL``."""

    settings.default_motion_model = DEFAULT_MOTION_MODEL
