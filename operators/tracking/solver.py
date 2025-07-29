from . import detect, track, cleanup, cycle, navigation

operator_classes = (
    *cycle.operator_classes,
    *track.operator_classes,
    *detect.operator_classes,
    *cleanup.operator_classes,
    *navigation.operator_classes,
)
