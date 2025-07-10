bl_info = {
    "name": "Tracking Tools",
    "description": "Collection of tracking operators including the tracking cycle",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

from importlib import import_module, reload


_modules = [
    "Combine",
    "sparse_marker_check",
    "motion_outlier_cleanup",
    "kaiser_track",
]

_loaded = []


def register():
    """Import and register all modules when the add-on is enabled."""
    global _loaded
    pkg = __name__
    for name in _modules:
        mod = import_module(f".{name}", package=pkg)
        reload(mod)
        if hasattr(mod, "register"):
            mod.register()
        _loaded.append(mod)


def unregister():
    """Unregister modules in reverse order."""
    for mod in reversed(_loaded):
        if hasattr(mod, "unregister"):
            mod.unregister()
    _loaded.clear()


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()

