bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz-Josef-Danner",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "Movie Clip Editor > Sidebar > Kaiserlich Tracker",
    "description": "Berechnungen und Marker-Erkennung für Tracking.",
    "warning": "",
    "category": "Tracking"
}

import importlib
from .tracking.UI import ui
from .tracking.Operator import operator

modules = [ui, operator]

def register():
    for m in modules:
        importlib.reload(m)
    for m in modules:
        if hasattr(m, 'register'):
            m.register()


def unregister():
    for m in reversed(modules):
        if hasattr(m, 'unregister'):
            m.unregister()
