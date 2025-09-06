import bpy
from . import overlay as _overlay
from . import solve_log as _solve_log  # stellt nur Funktionen bereit
from . import utils as _utils          # Hilfsfunktionen (Redraw)

# Unregister-Reihenfolge: Overlay zuerst runterfahren
_MODULES = [_overlay, _menus, _panels]

def register():
    for m in _MODULES:
        if hasattr(m, "register"):
            m.register()

def unregister():
    for m in reversed(_MODULES):
        if hasattr(m, "unregister"):
            try: m.unregister()
            except Exception: pass