import bpy


def set_tracking_channels(clip, red=None, green=None, blue=None):
    """Set default tracking channel flags on the given clip."""
    settings = clip.tracking.settings
    if red is not None:
        settings.use_default_red_channel = red
    if green is not None:
        settings.use_default_green_channel = green
    if blue is not None:
        settings.use_default_blue_channel = blue
