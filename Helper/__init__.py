from __future__ import annotations
import bpy

# Nur was für die Registrierung nötig ist:
from .set_test_value import set_test_value

try:
    from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal
except Exception:
    CLIP_OT_optimize_tracking_modal = None

__all__ = ("register", "unregister", "CLIP_OT_optimize_tracking_modal")

_classes = []
if CLIP_OT_optimize_tracking_modal is not None:
    _classes.append(CLIP_OT_optimize_tracking_modal)

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
