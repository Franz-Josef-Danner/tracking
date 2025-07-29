# Relative import to the tracking operator package and proxy operators
from . import (
    proxy,
    tracking,
    cleanup_tracks,
    setup_defaults,
    setup_test_defaults,
    tests,
    error_value,
    api_functions,
)

operator_classes = (
    *proxy.operator_classes,
    *tracking.operator_classes,
    *cleanup_tracks.operator_classes,
    *setup_defaults.operator_classes,
    *setup_test_defaults.operator_classes,
    *tests.operator_classes,
    *error_value.operator_classes,
    *api_functions.operator_classes,
)
