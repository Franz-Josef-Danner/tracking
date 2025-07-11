"""Helper utilities for counting NEW_ markers in a clip."""


def count_new_markers(clip, prefix="NEW_"):
    """Return the number of tracks starting with ``prefix``."""
    return sum(1 for t in clip.tracking.tracks if t.name.startswith(prefix))
