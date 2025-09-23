# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations
import bpy
from bpy.types import Operator

from .orchestrator import run_autotrack


class CLIP_OT_kaiserlich_coordinator_launcher(Operator):
    bl_idname = "clip.kaiserlich_coordinator_launcher"
    bl_label = "Kaiserlich Coordinator starten"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            # Versuche den aktiven Clip zu ermitteln
            clip = getattr(getattr(context, "space_data", None), "clip", None)
            if clip is None and bpy.data.movieclips:
                clip = next(iter(bpy.data.movieclips), None)
            if clip is None:
                self.report({"ERROR"}, "Kein Movie Clip gefunden.")
                return {"CANCELLED"}

            # Orchestrator starten (aktuell Stub/NotImplemented in orchestrator.py)
            try:
                result = run_autotrack(context, clip)
                self.report({"INFO"}, f"Autotrack gestartet – Ergebnis: {result}")
            except NotImplementedError:
                self.report({"WARNING"}, "Orchestrator noch nicht implementiert.")
            except Exception as ex:
                self.report({"ERROR"}, f"Autotrack-Fehler: {ex}")
                return {"CANCELLED"}

            return {"FINISHED"}
        except Exception as e:
            self.report({"ERROR"}, f"Fehler: {e}")
            return {"CANCELLED"}


_CLASSES = [
    CLIP_OT_kaiserlich_coordinator_launcher,
]


def register():
    for c in _CLASSES:
        try:
            bpy.utils.register_class(c)
        except Exception:
            pass


def unregister():
    for c in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
