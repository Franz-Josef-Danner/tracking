import bpy
from . import overlay as _overlay
from . import solve_log as _solve_log  # stellt nur Funktionen bereit
from . import utils as _utils          # Hilfsfunktionen (Redraw)
from .overlay_impl import ensure_overlay_handlers, remove_overlay_handlers
from .repeat_overlay import enable_repeat_overlay, disable_repeat_overlay

# Unregister-Reihenfolge: Overlay zuerst runterfahren
_MODULES = [_overlay]

# ---- EXPORTS FÜR ANDERE MODULE --------------------------------------------
# Damit tracking_coordinator._solve_log(context, v) das Root-Modul findet:
# __init__.kaiserlich_solve_log_add -> solve_log.kaiserlich_solve_log_add
kaiserlich_solve_log_add = _solve_log.kaiserlich_solve_log_add


class KC_OT_OverlayToggle(bpy.types.Operator):
    bl_idname = "kc.overlay_toggle"
    bl_label = "Standard-Overlay umschalten"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        scn = context.scene
        enabled = getattr(scn, "kaiserlich_solve_graph_enabled", False)
        scn.kaiserlich_solve_graph_enabled = not enabled
        if scn.kaiserlich_solve_graph_enabled:
            ensure_overlay_handlers()
        else:
            remove_overlay_handlers()
        return {'FINISHED'}


class KC_PT_OverlayPanel(bpy.types.Panel):
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"
    bl_label = "Overlay"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("kc.overlay_toggle", text="Standard-Overlay umschalten")
        col.separator()
        col.prop(context.scene, "kc_show_repeat_overlay", text="Repeat-Kurve anzeigen")
        col.prop(context.scene, "kc_repeat_overlay_height", text="Repeat-Kurvenhöhe")


def register():
    for m in _MODULES:
        if hasattr(m, "register"):
            m.register()
    bpy.utils.register_class(KC_PT_OverlayPanel)
    bpy.utils.register_class(KC_OT_OverlayToggle)
    # Szene-Properties registrieren (ohne auf bpy.context.scene zuzugreifen)
    from ..Helper.properties import ensure_repeat_overlay_props
    ensure_repeat_overlay_props()
    # Kein Auto-Enable zur Register-Zeit – Kontext ist ggf. eingeschränkt (Preferences).


def unregister():
    # Beim Unregister sauber entfernen
    try:
        disable_repeat_overlay()
    except Exception:
        pass
    bpy.utils.unregister_class(KC_OT_OverlayToggle)
    bpy.utils.unregister_class(KC_PT_OverlayPanel)
    for m in reversed(_MODULES):
        if hasattr(m, "unregister"):
            try:
                m.unregister()
            except Exception:
                pass
