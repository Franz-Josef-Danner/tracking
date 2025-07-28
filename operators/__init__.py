# Relative import to the tracking operator package
from . import tracking, proxy

operator_classes = (
    *proxy.operator_classes,
    *tracking.operator_classes,
)
