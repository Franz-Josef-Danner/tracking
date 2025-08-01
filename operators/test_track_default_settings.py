"""Test script to set default Blender tracking settings."""

import bpy


def main(context=None):
    """Set default tracking settings for the active clip."""
    if context is None:
        context = bpy.context

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("Kein aktiver Movie Clip gefunden")
        return {'CANCELLED'}

    settings = clip.tracking.settings

    # Auflösung des Movie Clips auslesen
    width = clip.size[0]

    # Neue Berechnungen für Pattern- und Suchgröße
    pattern_size = int(width / 500)
    search_size = pattern_size * 2

    settings.default_pattern_size = pattern_size
    settings.default_search_size = search_size
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

    print(
        f"Tracking-Defaults gesetzt (Pattern: {pattern_size}, Search: {search_size})"
    )
    return {'FINISHED'}


if __name__ == "__main__":
    main()
