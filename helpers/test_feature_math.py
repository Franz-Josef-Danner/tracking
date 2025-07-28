from .feature_math import (
    calculate_base_values,
    apply_threshold_to_margin_and_distance,
    marker_target_aggressive,
    marker_target_conservative,
)


def test_base_values():
    margin_base, min_distance_base = calculate_base_values(4000)
    assert margin_base == 100
    assert min_distance_base == 200


def test_threshold_scaling():
    margin, distance = apply_threshold_to_margin_and_distance(0.5, 100, 200)
    assert margin == 50
    assert distance == 100


def test_marker_aggressive():
    assert marker_target_aggressive(100) == 400


def test_marker_conservative():
    assert marker_target_conservative(90) == 30
    assert marker_target_conservative(2) == 1
