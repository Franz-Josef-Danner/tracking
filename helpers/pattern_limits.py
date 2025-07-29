from .pattern_base import pattern_base


def pattern_limits(clip):
    """Return minimum and maximum pattern size for a clip."""
    base = pattern_base(clip)
    min_size = int(base / 3)
    max_size = int(base * 3)
    return min_size, max_size
