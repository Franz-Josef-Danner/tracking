
def set_tracking_channels(settings, red=True, green=True, blue=True):
    """Set active color channels for tracking settings."""
    settings.use_default_red_channel = red
    settings.use_default_green_channel = green
    settings.use_default_blue_channel = blue
