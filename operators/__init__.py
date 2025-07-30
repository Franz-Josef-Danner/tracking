# Relative import to the tracking operator package and proxy operators
from . import (
    proxy,
    tracking,
    cleanup_tracks,
    cleanup_operator,
    test_setup_defaults,
    test_variants,
)

from ..helpers import (
    track_default_settings,
    error_value_operator,
)

operator_classes = (
    *proxy.operator_classes,
    *tracking.operator_classes,
    *cleanup_tracks.operator_classes,
    *cleanup_operator.operator_classes,
    *test_setup_defaults.operator_classes,
    *test_variants.operator_classes,
    *track_default_settings.operator_classes,
    *error_value_operator.operator_classes,
)
