"""Kaiserlich Tracker – Blender Add-on

Umsetzung des bereitgestellten Pseudocodes als modularer Prototyp.
Hinweis: Dieses Add-on ist für den Movie Clip Editor gedacht. Die
Operatoren erwarten einen aktiven MovieClip im Tracking-Kontext.

Da in dieser Umgebung Blender nicht ausgeführt wird, konnte der Code
nicht live verifiziert werden. Kleinere API-Anpassungen (v. a. bei
delete_marker) können in Blender erforderlich sein.
"""

bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner / AI Assist",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "Movie Clip Editor > Sidebar > Kaiserlich",
    "description": "Automatisierter Marker-Detektions-Zyklus mit Steuerlogik",
    "category": "Tracking",
}

import bpy

from . import ui
from .operator.detect_cycle import KAISERLICH_OT_detect_cycle


def register():
    bpy.utils.register_class(KAISERLICH_OT_detect_cycle)
    ui.register()


def unregister():
    ui.unregister()
    bpy.utils.unregister_class(KAISERLICH_OT_detect_cycle)


if __name__ == "__main__":
    register()
