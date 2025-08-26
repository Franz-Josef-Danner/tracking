# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/__init__.py – Function + Operator Registrar (aktualisiert)

- Exportiert Funktions-API (z. B. track_to_scene_end_fn, start_refine_modal).
- Registriert IMMER:
    * CLIP_OT_bidirectional_track
    * CLIP_OT_refine_high_error_modal  (neuer Modal-Operator)
- Optionale Operatoren: optimize_tracking_modal, marker_helper_main
"""
from __future__ import annotations
import bpy

# --- Funktions-API -----------------------------------------------------------
from .tracking_helper import track_to_scene_end_fn  # noqa: F401

# Refine (NEU: Modal-Operator + Startfunktion)
from .refine_high_error import CLIP_OT_refine_high_error_modal, start_refine_modal  # noqa: F401

# --- Feste Operatoren --------------------------------------------------------
from .bidirectional_track import CLIP_OT_bidirectional_track

# --- Optionale Operatoren ----------------------------------------------------
try:
    from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal  # type: ignore
except Exception:
    CLIP_OT_optimize_tracking_modal = None  # type: ignore

try:
    from .marker_helper_main import CLIP_OT_marker_helper_main  # type: ignore
except Exception:
    CLIP_OT_marker_helper_main = None  # type: ignore

# --- Exportliste -------------------------------------------------------------
__all__ = [
    "track_to_scene_end_fn",
    "start_refine_modal",
    "register",
    "unregister",
    "CLIP_OT_bidirectional_track",
    "CLIP_OT_refine_high_error_modal",
]

# --- Registrierlisten --------------------------------------------------------
_FIXED_CLASSES = [
    CLIP_OT_bidirectional_track,
    CLIP_OT_refine_high_error_modal,
]

_OPTIONAL_CLASSES = []
if CLIP_OT_optimize_tracking_modal is not None:
    _OPTIONAL_CLASSES.append(CLIP_OT_optimize_tracking_modal)
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
    for cls in reversed(_OPTIONAL_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    for cls in reversed(_FIXED_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    assert callable(track_to_scene_end_fn)
    assert callable(start_refine_modal)
