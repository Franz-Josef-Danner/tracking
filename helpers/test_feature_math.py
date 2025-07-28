from .feature_math import (
    calculate_base_values,
    apply_threshold_to_margin_and_distance,
)


def test_base_values():
    margin_base, min_distance_base = calculate_base_values(4000)
    assert margin_base == 100
    assert min_distance_base == 200


def test_threshold_scaling():
    margin, distance = apply_threshold_to_margin_and_distance(0.5, 100, 200)
    assert margin == 50
    assert distance == 100
