# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/__init__.py – Function + Operator Registrar (aktualisiert)

- Exportiert Funktions-API (z. B. track_to_scene_end_fn, start_refine_modal).
- Registriert IMMER:
    * CLIP_OT_bidirectional_track
    * CLIP_OT_refine_high_error_modal  (neuer Modal-Operator)
- Optionale Operatoren: marker_helper_main
"""
from __future__ import annotations
import bpy


from .bidirectional_track import CLIP_OT_bidirectional_track
from .reset_state import (
    reset_for_new_cycle,
    CLIP_OT_reset_runtime_state,
)  # re-export

# --- Optionale Operatoren ----------------------------------------------------
try:
    from .marker_helper_main import CLIP_OT_marker_helper_main  # type: ignore
except Exception:
    CLIP_OT_marker_helper_main = None  # type: ignore

# --- Exportliste -------------------------------------------------------------
__all__ = [
    "register",
    "unregister",
    "CLIP_OT_bidirectional_track",
    "reset_for_new_cycle",
    "CLIP_OT_reset_runtime_state",
]

# --- Registrierlisten --------------------------------------------------------
_FIXED_CLASSES = [
    CLIP_OT_bidirectional_track,
    CLIP_OT_reset_runtime_state,
]

_OPTIONAL_CLASSES = []
if CLIP_OT_marker_helper_main is not None:
    _OPTIONAL_CLASSES.append(CLIP_OT_marker_helper_main)

# --- Register/Unregister -----------------------------------------------------
def register() -> None:
    for cls in _FIXED_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass

    for cls in _OPTIONAL_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass

def unregister() -> None:
    # Zuerst optionale Klassen rückwärts abmelden
    for cls in reversed(_OPTIONAL_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    # Danach fixe Klassen rückwärts abmelden (verhindert "already registered" beim Reload)
    for cls in reversed(_FIXED_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    assert callable(track_to_scene_end_fn)
