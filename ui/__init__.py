import bpy
from . import overlay as _overlay
from . import solve_log as _solve_log  # stellt nur Funktionen bereit
from . import utils as _utils          # Hilfsfunktionen (Redraw)

# Unregister-Reihenfolge: Overlay zuerst runterfahren
_MODULES = [_overlay]

# ---- EXPORTS FÜR ANDERE MODULE --------------------------------------------
# Damit tracking_coordinator._solve_log(context, v) das Root-Modul findet:
# __init__.kaiserlich_solve_log_add -> solve_log.kaiserlich_solve_log_add
kaiserlich_solve_log_add = _solve_log.kaiserlich_solve_log_add

def register():
    for m in _MODULES:
        if hasattr(m, "register"):
            m.register()

def unregister():
    for m in reversed(_MODULES):
        if hasattr(m, "unregister"):
            try: m.unregister()
            except Exception: pass
