bl_info = {
    "name": "Tracking Tools",
    "description": "Collection of tracking operators including the tracking cycle",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

from . import combined_cycle
from . import distance_remove


def register():
    combined_cycle.register()
    distance_remove.register()


def unregister():
    combined_cycle.unregister()
    distance_remove.unregister()

