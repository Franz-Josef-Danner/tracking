bl_info = {
    "name": "Tracking Tools",
    "description": "Collection of tracking operators including the tracking cycle",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

from . import combined_cycle
from . import sparse_marker_check
from . import motion_outlier_cleanup


def register():
    combined_cycle.register()
    sparse_marker_check.register()
    motion_outlier_cleanup.register()


def unregister():
    motion_outlier_cleanup.unregister()
    sparse_marker_check.unregister()
    combined_cycle.unregister()


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()

