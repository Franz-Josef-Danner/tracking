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
from . import properties
from .operators import operator as kt_operator
from .UI import ui as kt_ui

modules = [properties, kt_operator, kt_ui]


def register():
    for m in modules:
        importlib.reload(m)
    properties.register()
    kt_operator.register()
    kt_ui.register()


def unregister():
    kt_ui.unregister()
    kt_operator.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
