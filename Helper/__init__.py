# Helper/__init__.py (Minimal-Registrar + optionaler Operator)
from __future__ import annotations
import bpy

from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal

# OPTIONAL: wenn du marker_helper_main als Operator registriert hast:
try:
    from .marker_helper_main import CLIP_OT_marker_helper_main
except Exception:
    CLIP_OT_marker_helper_main = None

__all__ = ("register", "unregister", "CLIP_OT_optimize_tracking_modal")

_classes = []
if CLIP_OT_optimize_tracking_modal:
    _classes.append(CLIP_OT_optimize_tracking_modal)
if CLIP_OT_marker_helper_main:  # nur falls vorhanden
    _classes.append(CLIP_OT_marker_helper_main)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    print("[Helper] register() OK")

def unregister():
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    print("[Helper] unregister() OK")
