import bpy


def set_tracking_channels(red: bool = True, green: bool = True, blue: bool = True) -> None:
    """Set the RGB channels used for tracking operations."""
    settings = bpy.context.scene.tracking_settings

    settings.use_red_channel = red
    settings.use_green_channel = green
    settings.use_blue_channel = blue

    print(f"\U0001F39A️ RGB-Kan\u00e4le gesetzt: R={red}, G={green}, B={blue}")
