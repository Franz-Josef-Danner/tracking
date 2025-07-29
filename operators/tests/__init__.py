from . import pattern, motion, channel

operator_classes = (
    *pattern.operator_classes,
    *motion.operator_classes,
    *channel.operator_classes,
)
