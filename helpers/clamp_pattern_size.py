from .pattern_limits import pattern_limits


def clamp_pattern_size(value, clip):
    min_size, max_size = pattern_limits(clip)
    return max(min(value, max_size), min_size)
