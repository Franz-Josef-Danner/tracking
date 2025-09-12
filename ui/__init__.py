# SPDX-License-Identifier: GPL-2.0-or-later
"""UI module for Kaiserlich repeat scope overlay."""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, IntProperty

from .repeat_scope import enable_repeat_scope, disable_repeat_scope


# --- Prop-Update: schaltet den Draw-Handler an/aus ---
def _kc_update_scope(self, ctx):
    try:
        enable_repeat_scope(bool(ctx.scene.kc_show_repeat_scope), source="prop_update")
    except Exception as e:  # pragma: no cover - defensive log
        print("[KC] _kc_update_scope failed:", e)


# --- Beim Laden .blend: Zustand synchronisieren + evtl. TMP-Handler entsorgen ---
@persistent
def _kc_load_post(_dummy):
    try:
        # evtl. alter Konsolen-Test-Handler aus driver_namespace entfernen
        ns = bpy.app.driver_namespace
        hdl = ns.get("_KC_TMP_SCOPE_HDL")
        if hdl:
            try:
                bpy.types.SpaceClipEditor.draw_handler_remove(hdl, "WINDOW")
            except Exception:
                pass
            ns["_KC_TMP_SCOPE_HDL"] = None

        s = bpy.context.scene
        val = getattr(s, "kc_show_repeat_scope", False)
        enable_repeat_scope(bool(val), source="load_post")
    except Exception as e:  # pragma: no cover - defensive log
        print("[KC] _kc_load_post failed:", e)


class KAISERLICH_PT_repeat_scope(bpy.types.Panel):
    """Panel to configure the repeat scope overlay."""

    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"
    bl_label = "Repeat Scope"

    def draw(self, context):
        layout = self.layout
        s = context.scene
        layout.prop(s, "kc_show_repeat_scope")
        col = layout.column(align=True)
        col.prop(s, "kc_repeat_scope_height")
        col.prop(s, "kc_repeat_scope_bottom")
        col.prop(s, "kc_repeat_scope_margin_x")
        col.prop(s, "kc_repeat_scope_show_cursor")


# --- Registrierung ---
classes = (KAISERLICH_PT_repeat_scope,)


def register() -> None:
    """Register UI components and scene properties."""

    # Scene-Properties (existieren vor Panel.draw -> keine rna_uiItemR-Fehler)
    bpy.types.Scene.kc_show_repeat_scope = BoolProperty(
        name="Repeat Scope",
        description="Overlay anzeigen",
        default=False,
        update=_kc_update_scope,
    )

    bpy.types.Scene.kc_repeat_scope_height = IntProperty(
        name="Höhe", default=140, min=40, max=800
    )

    bpy.types.Scene.kc_repeat_scope_bottom = IntProperty(
        name="Abstand unten", default=24, min=0, max=2000
    )

    bpy.types.Scene.kc_repeat_scope_margin_x = IntProperty(
        name="Rand X", default=12, min=0, max=2000
    )

    bpy.types.Scene.kc_repeat_scope_show_cursor = BoolProperty(
        name="Cursor anzeigen", default=True
    )

    for cls in classes:
        bpy.utils.register_class(cls)

    # load_post anhängen (nur einmal)
    if _kc_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_kc_load_post)

    # Erstregistrierung: Zustand initial synchronisieren
    try:
        enable_repeat_scope(
            bool(bpy.context.scene.kc_show_repeat_scope), source="register"
        )
    except Exception:
        pass


def unregister() -> None:
    """Unregister components and clean up handlers."""

    # Overlay aus
    try:
        disable_repeat_scope(source="unregister")
    except Exception:
        pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

    # Props entfernen (falls vorhanden)
    for name in (
        "kc_show_repeat_scope",
        "kc_repeat_scope_height",
        "kc_repeat_scope_bottom",
        "kc_repeat_scope_margin_x",
        "kc_repeat_scope_show_cursor",
    ):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)

    # Handler abklemmen
    if _kc_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_kc_load_post)

