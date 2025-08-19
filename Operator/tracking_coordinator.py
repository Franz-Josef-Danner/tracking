# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py – Funktionsvariante (keine Helper-Operator-Registration)

- Ruft **direkt die Helper-Funktion** `track_to_scene_end_fn(context, coord_token=...)` auf,
  die intern `bpy.ops.clip.track_markers('INVOKE_DEFAULT', ...)` ausführt.
- **Kein** Modal-/Timer-Loop mehr nötig – die Funktion liefert nach Abschluss ein Info-Dict zurück.
- Gibt danach "Finish" aus.
"""
from __future__ import annotations

from time import time_ns
from typing import Set

import bpy

# Direkter Funktionsimport aus dem Helper-Paket
from ..Helper.tracking_helper import track_to_scene_end_fn  # type: ignore

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Startet das Tracking über die **Funktion** und meldet danach Finish."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (function call)"
    bl_description = (
        "Ruft track_to_scene_end_fn auf (Forward, Sequence, INVOKE_DEFAULT) und meldet danach 'Finish'."
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        token = str(time_ns())
        try:
            info = track_to_scene_end_fn(context, coord_token=token)
        except Exception as ex:
            self.report({'ERROR'}, f"Helper-Fehler: {ex}")
            return {"CANCELLED"}

        # Optionales Logging der Rückgabe
        try:
            self.report({'INFO'}, f"Tracking done: start={info.get('start_frame')} → {info.get('tracked_until')}")
        except Exception:
            pass

        self.report({'INFO'}, "Finish")
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
    print("[Coordinator] registered (function variant)")


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    print("[Coordinator] unregistered")
