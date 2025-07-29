import re


def strip_prefix(name):
    """Remove an existing uppercase prefix from a track name."""
    return re.sub(r'^[A-Z]+_', '', name)
