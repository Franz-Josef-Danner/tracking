# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py

Minimal: Ruft ausschließlich den Track‑Helper auf, der vorwärts bis zum
Szenenende läuft (mit initialem INVOKE_DEFAULT).

Keine Pre-Hooks, keine Zusatzfunktionen – nur der direkte Trigger.
"""
from __future__ import annotations

import bpy
from typing import Set

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


# ------------------------------------------------------------
# Import des Track-Helpers (robust für verschiedene Paket-Layouts)
# ------------------------------------------------------------
try:
    # bevorzugt: Unterpaket Helper/
    from ..Helper.tracking_helper import (
        helper_track_forward_to_scene_end_invoke_default as _run_track_helper,
    )
except Exception:
    try:
        # evtl. direkt im Paket
        from ..tracking_helper import (
            helper_track_forward_to_scene_end_invoke_default as _run_track_helper,
        )
    except Exception:
        # Fallback: lokales/externes Modul im PYTHONPATH
        from tracking_helper import (
            helper_track_forward_to_scene_end_invoke_default as _run_track_helper,
        )


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Startet nur den Track‑Helper (vorwärts bis Szenenende)."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Track to Scene End)"
    bl_description = (
        "Startet den Track‑Helper: vorwärts tracken bis zum Szenenende."
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Minimal: Nur im Clip-Editor verfügbar.
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        try:
            _run_track_helper()  # ruft den Helper-Operator intern auf
            return {"FINISHED"}
        except Exception as ex:
            self.report({'ERROR'}, f"Track-Helper-Fehler: {ex}")
            return {"CANCELLED"}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # Spiegelung für Scripting
        return self.invoke(context, None)


# ----------
# Register
# ----------
_classes = (CLIP_OT_tracking_coordinator,)

def register():
    for c in _classes:
        bpy.utils.register_class(c)
    print("[Coordinator] registered (Track‑Helper only)")


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
    print("[Coordinator] unregistered")
