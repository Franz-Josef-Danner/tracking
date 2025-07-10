bl_info = {
    "name": "Tracking Tools",
    "description": "Collection of tracking operators including the tracking cycle",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

import bpy
from . import combined_cycle
from . import sparse_marker_check
from . import motion_outlier_cleanup
from . import detect
from . import track
from . import refine
from . import playhead
from . import distance_remove
from . import error_cleaneup
from . import track_marker_size_adapt

from .combined_cycle import CLIP_PT_tracking_cycle_panel


def register():
    combined_cycle.register()
    sparse_marker_check.register()
    motion_outlier_cleanup.register()
    detect.register()
    track.register()
    refine.register()
    playhead.register()
    distance_remove.register()
    error_cleaneup.register()
    track_marker_size_adapt.register()
    bpy.utils.register_class(CLIP_PT_tracking_cycle_panel)


def unregister():
    bpy.utils.unregister_class(CLIP_PT_tracking_cycle_panel)
    track_marker_size_adapt.unregister()
    error_cleaneup.unregister()
    distance_remove.unregister()
    playhead.unregister()
    refine.unregister()
    track.unregister()
    detect.unregister()
    motion_outlier_cleanup.unregister()
    sparse_marker_check.unregister()
    combined_cycle.unregister()


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()

