import bpy
from .utils import NF, DEFAULT_MARKER_FRAME, DEFAULT_MOTION_MODEL
from .pattern_limits import pattern_limits
from .clamp_pattern_size import clamp_pattern_size
from .cycle_motion_model import cycle_motion_model


def _update_nf_and_motion_model(frame, clip):
    """Maintain NF list and adjust motion model and pattern size."""
    settings = clip.tracking.settings
    scene = bpy.context.scene
    min_size, max_size = pattern_limits(clip)
    if frame in NF:
        cycle_motion_model(settings, clip, reset_size=False)
        if settings.default_pattern_size < max_size:
            settings.default_pattern_size = min(
                int(settings.default_pattern_size * 1.1),
                max_size,
            )
        else:
            max_mf = DEFAULT_MARKER_FRAME * 2
            scene.marker_frame = min(int(scene.marker_frame * 1.1), max_mf)
    else:
        NF.append(frame)
        settings.default_motion_model = DEFAULT_MOTION_MODEL
        settings.default_pattern_size = int(settings.default_pattern_size * 0.9)
        if settings.default_pattern_size < max_size and scene.marker_frame > DEFAULT_MARKER_FRAME:
            scene.marker_frame = max(int(scene.marker_frame * 0.9), DEFAULT_MARKER_FRAME)
    settings.default_pattern_size = clamp_pattern_size(settings.default_pattern_size, clip)
    settings.default_search_size = settings.default_pattern_size * 2
