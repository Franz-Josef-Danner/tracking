import bpy
from . import overlay as _overlay
from . import solve_log as _solve_log  # stellt nur Funktionen bereit
from . import utils as _utils          # Hilfsfunktionen (Redraw)


def _register_scene_props():
    """Zusätzliche Scene-Properties für das Solve-Log-Panel."""
    from bpy.props import BoolProperty, IntProperty

    scn = bpy.types.Scene
    # Auto-Row-Steuerung für Solve-Log-Panel
    scn.kaiserlich_solve_log_auto_rows = BoolProperty(
        name="Auto Rows",
        description="Höhe der Liste passt sich der Anzahl Einträge an",
        default=True,
    )
    scn.kaiserlich_solve_log_min_rows = IntProperty(
        name="Min Rows",
        default=5,
        min=1,
        max=50,
        description="Mindestzeilen für die Solve-Log-Liste",
    )
    scn.kaiserlich_solve_log_max_rows = IntProperty(
        name="Max Rows",
        default=30,
        min=5,
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
    for attr in (
        "kaiserlich_solve_log_auto_rows",
        "kaiserlich_solve_log_min_rows",
        "kaiserlich_solve_log_max_rows",
    ):
        try:
            delattr(bpy.types.Scene, attr)
        except Exception:
            pass
