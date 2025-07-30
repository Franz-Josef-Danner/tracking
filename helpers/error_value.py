from .error_value_operator import calculate_clip_error


def error_value(clip):
    """Return summed error of all marker positions."""
    return calculate_clip_error(clip)
