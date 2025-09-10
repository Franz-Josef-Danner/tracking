import bpy
from . import overlay as _overlay
from . import solve_log as _solve_log  # stellt nur Funktionen bereit
from . import utils as _utils          # Hilfsfunktionen (Redraw)


def _register_scene_props():
    """Zusätzliche Scene-Property für das Solve-Log-Panel."""
    from bpy.props import IntProperty

    scn = bpy.types.Scene
    # Maximale Listenhöhe des Solve-Logs
    scn.kaiserlich_solve_log_max_rows = IntProperty(
        name="Max Rows",
        default=30,
        min=1,
        max=200,
        description="Maximalzeilen für die Solve-Log-Liste (Panel-Höhenlimit)",
    )


# Unregister-Reihenfolge: Overlay zuerst runterfahren
_MODULES = [_overlay, _solve_log]

# ---- EXPORTS FÜR ANDERE MODULE --------------------------------------------
# Damit tracking_coordinator._solve_log(context, v) das Root-Modul findet:
# __init__.kaiserlich_solve_log_add -> solve_log.kaiserlich_solve_log_add
kaiserlich_solve_log_add = _solve_log.kaiserlich_solve_log_add


def register():
    _register_scene_props()
    for m in _MODULES:
        if hasattr(m, "register"):
            m.register()


def unregister():
    for m in reversed(_MODULES):
        if hasattr(m, "unregister"):
            try:
                m.unregister()
            except Exception:
                pass
    # optional: Props entfernen
    try:
        delattr(bpy.types.Scene, "kaiserlich_solve_log_max_rows")
    except Exception:
        pass
