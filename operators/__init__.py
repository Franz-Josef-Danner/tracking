# Relative import to the tracking operator package and proxy operators
from . import (
    proxy,
    tracking,
    cleanup_tracks,
    setup_defaults,
    setup_test_defaults,
    tracking_default_settings_operator,
    tests,
    error_value,
)

operator_classes = (
    *proxy.operator_classes,
    *tracking.operator_classes,
    *cleanup_tracks.operator_classes,
    *setup_defaults.operator_classes,
    *setup_test_defaults.operator_classes,
    *tracking_default_settings_operator.operator_classes,
    *tests.operator_classes,
    *error_value.operator_classes,
)
