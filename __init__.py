bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz-Josef Danner",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "Movie Clip Editor > Sidebar > Kaiserlich Tracker",
    "description": "Panel mit Parameter 'Marker per Frame' und Button 'Detect Cyclus'",
    "warning": "",
    "category": "Tracking",
}

import importlib

# Globale Referenzen für Module (werden lazy geladen)
_modules = {}


def _load_modules(reload=False):
    from . import properties  # noqa: F401
    from .operators import operator as kt_operator  # noqa: F401
    from .UI import ui as kt_ui  # noqa: F401

    mods = {
        'properties': properties,
        'kt_operator': kt_operator,
        'kt_ui': kt_ui,
    }
    if reload:
        for m in mods.values():
            importlib.reload(m)
    _modules.update(mods)


def register():
    # Beim Nachladen (F8) existieren Module schon -> reload erzwingen
    reload_flag = bool(_modules)
    _load_modules(reload=reload_flag)
    _modules['properties'].register()
    _modules['kt_operator'].register()
    _modules['kt_ui'].register()


def unregister():
    if not _modules:
        return
    _modules['kt_ui'].unregister()
    _modules['kt_operator'].unregister()
    _modules['properties'].unregister()

