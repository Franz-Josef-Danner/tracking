# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py – Coordinator, der den Optimize-Flow startet

• Startet **CLIP_OT_optimize_tracking_modal** per INVOKE_DEFAULT.
• Keine eigenen Detect/Track-Aufrufe mehr; das übernimmt der Helper-basierte Optimize-Operator.
• Bleibt im UI simpel (ein Button / F3-Eintrag), Log-Meldungen für Start/Finish.
"""
from __future__ import annotations

from typing import Set
import bpy

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Optimize)"
    bl_description = (
        "Startet den optimierten Detect→Track-Flow (nur Funktionen innen)."
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        # Übergibt keine weiteren Parameter – Optimize liest origin-frame aus scene
        try:
            self.report({'INFO'}, "Starte Optimize-Flow…")
            # WICHTIG: INVOKE_DEFAULT, damit der Optimize-Operator seinen Modal-Loop registriert
            bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
        except Exception as ex:
            self.report({'ERROR'}, f"Start fehlgeschlagen: {ex}")
            return {"CANCELLED"}

        # Der eigentliche Ablauf passiert modal im Optimize-Operator.
        # Wir melden hier nur den Start; Finish wird vom Optimize-Operator geloggt.
        return {"FINISHED"}


# ----------
# Register
# ----------
_classes = (CLIP_OT_tracking_coordinator,)


def register():
    for c in _classes:
        try:
            bpy.utils.register_class(c)
        except ValueError:
            pass
    print("[Coordinator] registered (Optimize launcher)")


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    print("[Coordinator] unregistered")
