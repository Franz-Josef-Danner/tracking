# Relative import to the tracking operator package and proxy operators
from . import proxy, tracking

operator_classes = (
    *proxy.operator_classes,
    *tracking.operator_classes,
)
