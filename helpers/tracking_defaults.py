import bpy


def set_default_tracking_settings(context=None):
    """Setzt alle Tracking-Parameter laut Vorgabe."""
    if context is None:
        context = bpy.context
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("\u26a0\ufe0f Kein Clip geladen")
        return
    settings = clip.tracking.settings
    settings.default_pattern_size = 10
    settings.default_search_size = settings.default_pattern_size * 2
    settings.default_motion_model = 'Loc'
    settings.default_pattern_match = 'KEYFRAME'
    settings.use_default_brute = True
    settings.use_default_normalization = True
    settings.use_default_red_channel = True
    settings.use_default_green_channel = True
    settings.use_default_blue_channel = True
    settings.default_weight = 1.0
    settings.default_correlation_min = 0.9
    settings.default_margin = 10
