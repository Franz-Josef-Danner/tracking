import bpy
from .overlay_impl import ensure_overlay_handlers, remove_overlay_handlers
from .repeat_scope import enable_repeat_scope, disable_repeat_scope
class KC_OT_OverlayToggle(bpy.types.Operator):
    bl_idname = "kc.overlay_toggle"
    bl_label = "Standard-Overlay umschalten"
    bl_description = "Kaiserlich Overlay ein-/ausschalten"

    def execute(self, context):
        if not remove_overlay_handlers():
            ensure_overlay_handlers(context.scene)
        try:
            context.area.tag_redraw()
        except Exception:
            pass
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
        # Defensiv (Register-Phase in Preferences liefert eingeschränkten Kontext)
        if hasattr(bpy.types.Scene, "kc_show_repeat_scope") and hasattr(context.scene, "kc_show_repeat_scope"):
            col.prop(context.scene, "kc_show_repeat_scope", text="Repeat-Scope anzeigen")
            col.prop(context.scene, "kc_repeat_scope_height", text="Höhe (px)")
            col.prop(context.scene, "kc_repeat_scope_bottom", text="Abstand unten (px)")
            col.prop(context.scene, "kc_repeat_scope_margin_x", text="Seitenrand (px)")
        else:
            col.label(text="Scope-Props werden nach Register() initialisiert")


def register():
    bpy.utils.register_class(KC_PT_OverlayPanel)
    bpy.utils.register_class(KC_OT_OverlayToggle)
    # Szene-Properties (nur RNAs, ohne auf bpy.context zuzugreifen)
    from ..Helper.properties import ensure_repeat_scope_props
    ensure_repeat_scope_props()


def unregister():
    try:
        disable_repeat_scope()
    except Exception:
        pass
    bpy.utils.unregister_class(KC_OT_OverlayToggle)
    bpy.utils.unregister_class(KC_PT_OverlayPanel)
