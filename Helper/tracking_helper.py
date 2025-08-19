# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py

Minimaler Coordinator: ruft **ausschließlich** den simplen Track‑Helper‑Operator
`bw.track_simple_forward` auf, der den eingebauten Blender‑Operator
`bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)`
auslöst.

Anpassung: Import/Registrierung wurden auf `BW_OT_track_simple_forward`
umgestellt (vorher: BW_OT_track_to_scene_end).
"""
from __future__ import annotations

import bpy
from typing import Set, Optional
from importlib import import_module

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


# ------------------------------------------------------------
# Import/Registration des simplen Track‑Operators (bw.track_simple_forward)
# ------------------------------------------------------------
_BW_OP = None  # type: Optional[type]


def _try_import_candidates() -> Optional[type]:
    """Versucht die Operator‑Klasse `BW_OT_track_simple_forward` zu importieren.

    Unterstützte Layouts:
    - Paket/Helper/tracking_helper.py  →  ..Helper.tracking_helper
    - Paket/tracking_helper.py         →  ..tracking_helper
    - Direkt importierbar              →  tracking_helper
    """
    candidates = (
        ("..Helper.tracking_helper", True),
        ("..tracking_helper", True),
        ("tracking_helper", False),
    )
    for name, is_rel in candidates:
        try:
            mod = import_module(name, package=__package__) if is_rel else import_module(name)
            op = getattr(mod, "BW_OT_track_simple_forward", None)
            if op is not None:
                return op
        except Exception:
            pass
    return None


def _ensure_bw_op_registered() -> None:
    """Importiert und registriert `BW_OT_track_simple_forward` wenn nötig."""
    global _BW_OP
    if _BW_OP is None:
        _BW_OP = _try_import_candidates()
    if _BW_OP is None:
        raise RuntimeError(
            "Konnte BW_OT_track_simple_forward nicht importieren. Prüfe 'Helper/tracking_helper.py'."
        )
    try:
        bpy.utils.register_class(_BW_OP)
    except ValueError:
        # Bereits registriert → ok
        pass


# ------------------------------------------------------------
# Operator (Coordinator)
# ------------------------------------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Startet nur den simplen Track‑Helper (INVOKE_DEFAULT, backwards=False, sequence=True)."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Simple Forward)"
    bl_description = (
        "Löst den eingebauten Track-Operator aus (backwards=False, sequence=True)."
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Minimal: Nur im Clip‑Editor verfügbar (verhindert falschen Kontext).
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        try:
            _ensure_bw_op_registered()
            # UI‑konformer Aufruf des simplen Helpers
            bpy.ops.bw.track_simple_forward('INVOKE_DEFAULT')
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


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    # keine Self‑Tests nötig; Coordinator ohne UI nicht sinnvoll testbar
    pass
