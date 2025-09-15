# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations
import bpy

_STICKY_KEY = "_kc_repeat_scope_sticky"


class CLIP_OT_kc_toggle_repeat_scope_sticky(bpy.types.Operator):
    """Overlay-Zeichnung auch bei internem Toggle „kleben“ lassen"""
    bl_idname = "clip.kc_toggle_repeat_scope_sticky"
    bl_label = "Repeat-Scope fixieren"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):  # type: ignore[override]
        scn = context.scene
        cur = bool(scn.get(_STICKY_KEY, False))
        scn[_STICKY_KEY] = not cur
        state = "ON" if not cur else "OFF"
        print(f"[Scope][Sticky] set → {state}")
        try:
            # Handler bei Aktivierung sicherstellen
            if scn.get(_STICKY_KEY, False):
                from .repeat_scope import ensure_repeat_scope_handler
                ensure_repeat_scope_handler(scn)
        except Exception:
            pass
        # Redraw anstoßen
        try:
            for w in bpy.context.window_manager.windows:
                for a in w.screen.areas:
                    if a.type == 'CLIP_EDITOR':
                        for r in a.regions:
                            if r.type == 'WINDOW':
                                r.tag_redraw()
        except Exception:
            pass
        return {"FINISHED"}


class KC_PT_repeat_scope(bpy.types.Panel):
    """Repeat-Scope Overlay Einstellungen"""
    bl_label = "Kaiserlich: Repeat-Scope"
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"

    def draw(self, context: bpy.types.Context) -> None:  # type: ignore[override]
        layout = self.layout
        scn = context.scene

        box = layout.box()
        row = box.row(align=True)
        row.prop(scn, "kc_show_repeat_scope", text="Overlay anzeigen")
        sticky_flag = bool(scn.get(_STICKY_KEY, False))
        row.operator(
            CLIP_OT_kc_toggle_repeat_scope_sticky.bl_idname,
            text="Fixieren",
            icon="PINNED" if sticky_flag else "PINNED",
        )

        col = box.column(align=True)
        col.prop(scn, "kc_repeat_scope_height", text="Höhe")
        col.prop(scn, "kc_repeat_scope_bottom", text="Abstand unten")
        col.prop(scn, "kc_repeat_scope_margin_x", text="Seitenabstand")
        col.prop(scn, "kc_repeat_scope_levels", text="Levels")
        col.prop(scn, "kc_repeat_scope_show_cursor", text="Cursor-Linie")

        layout.separator()
        help_box = layout.box()
        help_box.label(text="Hinweise", icon="INFO")
        help_box.label(text="• Sticky hält das Overlay sichtbar, auch wenn intern getoggelt wird.")
        help_box.label(text="• Änderungen triggern Redraws; Logs im System Console prüfen.")


classes = (
    CLIP_OT_kc_toggle_repeat_scope_sticky,
    KC_PT_repeat_scope,
)


def register() -> None:
    from . import repeat_scope as _rs
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass
    try:
        if hasattr(_rs, "register"):
            _rs.register()
    except Exception:
        pass
    # Sicherstellen, dass der Draw-Handler nach Addon-Reload aktiv ist, falls aktiviert
    try:
        from .repeat_scope import ensure_repeat_scope_handler
        scn = bpy.context.scene
        ui_flag = bool(getattr(scn, "kc_show_repeat_scope", False))
        sticky = bool(scn.get(_STICKY_KEY, False))
        if ui_flag or sticky:
            ensure_repeat_scope_handler(scn)
            print("[Scope][UI] ensure handler after UI register")
    except Exception:
        pass


def unregister() -> None:
    from . import repeat_scope as _rs
    try:
        if hasattr(_rs, "unregister"):
            _rs.unregister()
    except Exception:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

