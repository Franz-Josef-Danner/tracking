bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "Video Sequence Editor > Sidebar",
    "description": "Tracking Hilfs-Addon",
    "category": "Animation",
}

import importlib
try:
    import bpy  # Blender Runtime
except Exception:  # pragma: no cover - außerhalb von Blender nicht verfügbar
    bpy = None

from .UI import ui as ui_module
from .Operator import operator as operator_module

modules = [ui_module, operator_module]


def register():
    for m in modules:
        importlib.reload(m)
    if bpy:
        # Modul-eigene Register Funktionen (Properties etc.)
        if hasattr(ui_module, "register"):
            ui_module.register()
        if hasattr(operator_module, "register"):
            operator_module.register()
        # Fallback: direkte Klassenregistrierung (falls nicht im Modul-Register enthalten)
        for cls in ui_module.classes + operator_module.classes:
            if not hasattr(bpy.types, cls.__name__):
                try:
                    bpy.utils.register_class(cls)
                except Exception:
                    pass


def unregister():
    if bpy:
        if hasattr(ui_module, "unregister"):
            try:
                ui_module.unregister()
            except Exception:
                pass
        if hasattr(operator_module, "unregister"):
            try:
                operator_module.unregister()
            except Exception:
                pass
        for cls in reversed(ui_module.classes + operator_module.classes):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass

__all__ = ["register", "unregister"]

if __name__ == "__main__":
    register()
