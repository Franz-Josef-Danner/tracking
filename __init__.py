bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "Clip Editor > Sidebar > Kaiserlich",
    "description": "Automatischer Feature-Detection-Zyklus mit dynamischen Parametern",
    "category": "Tracking"
}

import bpy

from .UI import ui
from .Operator import operator
from .Helper import bootstrap, snapshot, detect, newmarker, cleanup, delete, control

modules = (
    ui,
    operator,
    bootstrap,
    snapshot,
    detect,
    newmarker,
    cleanup,
    delete,
    control,
)


def register():
    for m in modules:
        if hasattr(m, 'register'):
            m.register()


def unregister():
    for m in reversed(modules):
        if hasattr(m, 'unregister'):
            m.unregister()

if __name__ == "__main__":
    register()
