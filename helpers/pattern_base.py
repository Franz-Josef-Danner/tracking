
def pattern_base(clip):
    """Return the default pattern size based on the clip width."""
    width, _ = clip.size
    return int(width / 100)
