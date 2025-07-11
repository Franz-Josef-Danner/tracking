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
from . import marker_count_property
from . import adjust_marker_count_plus
from . import proxy_marker_cycle


def register():
    combined_cycle.register()
    sparse_marker_check.register()
    motion_outlier_cleanup.register()
    marker_count_property.register()
    adjust_marker_count_plus.register()
    proxy_marker_cycle.register()


def unregister():
    proxy_marker_cycle.unregister()
    adjust_marker_count_plus.unregister()
    marker_count_property.unregister()
    motion_outlier_cleanup.unregister()
    sparse_marker_check.unregister()
    combined_cycle.unregister()


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()

