import bpy
from .repeat_scope import enable_repeat_scope, disable_repeat_scope


# Ensure properties exist before drawing panels (failsafe)
def _kc_props_ready():
    s = getattr(bpy.context, "scene", None)
    return bool(s and hasattr(s, "kc_show_repeat_scope"))


class KAISERLICH_PT_repeat_scope(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Kaiserlich'
    bl_label = 'Repeat Scope'

    def draw(self, context):
        layout = self.layout
        if not _kc_props_ready():
            layout.label(text="Initialisiere Properties…")
            return
        s = context.scene
        layout.prop(s, "kc_show_repeat_scope")
        col = layout.column(align=True)
        col.prop(s, "kc_repeat_scope_height")
        col.prop(s, "kc_repeat_scope_bottom")
        col.prop(s, "kc_repeat_scope_margin_x")
        col.prop(s, "kc_repeat_scope_show_cursor")


def register():
    bpy.utils.register_class(KAISERLICH_PT_repeat_scope)


def unregister():
    try:
        disable_repeat_scope()
    except Exception:
        pass
    bpy.utils.unregister_class(KAISERLICH_PT_repeat_scope)

