import bpy

def apply_marker_sizes(clip, pz: int, sz: int):

    if clip is None:
        return

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return

    settings = getattr(tracking, "settings", None)
    if settings is None:
        return

    # Blender verwendet pattern_size und search_size (Kantenlänge in Pixeln)
    settings.default_pattern_size = pz
    settings.default_search_size = sz