from . import pattern, channel
from .motion import CLIP_OT_test_motion

operator_classes = (
    CLIP_OT_test_motion,
    *pattern.operator_classes,
    *channel.operator_classes,
)
