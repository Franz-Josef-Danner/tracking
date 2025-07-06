bl_info = {
    "name": "Tracking Tools",
    "description": "Collection of tracking operators including the tracking cycle",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

from . import combined_cycle, single_frame_tracker


def register():
    combined_cycle.register()
    single_frame_tracker.register()


def unregister():
    single_frame_tracker.unregister()
    combined_cycle.unregister()


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()

