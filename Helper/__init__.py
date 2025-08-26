# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/__init__.py – Function + Operator Registrar

- Exportiert Funktions-API (z. B. track_to_scene_end_fn).
- Registriert IMMER den Bidirectional-Operator.
- Refine:
    * Neue Version liefert nur eine Funktion (refine_on_high_error) → kein Operator zu registrieren.
    * Falls später wieder ein Operator vorhanden ist (CLIP_OT_refine_high_error), wird er optional mit-registriert.
- Weitere optionale Operatoren (optimize, marker_helper_main) werden best-effort registriert.
"""
from __future__ import annotations
import bpy

# --- Funktions-API -----------------------------------------------------------
from .tracking_helper import track_to_scene_end_fn  # noqa: F401

# Refine (Funktions-API vorhanden, Operator evtl. nicht)
try:
    from .refine_high_error import refine_on_high_error  # neue Version: nur Funktion
except Exception:
    refine_on_high_error = None  # type: ignore

# Optional: falls die Datei doch (wieder) einen Operator enthält, sauber mitnehmen
try:
    from .refine_high_error import CLIP_OT_refine_high_error  # alte Version
except Exception:
    CLIP_OT_refine_high_error = None  # type: ignore

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

# Optional: Score/Frame-Utility aus alter Refine-Implementierung, wenn vorhanden
try:
    from .refine_high_error import compute_high_error_frames  # type: ignore
except Exception:
    compute_high_error_frames = None  # type: ignore


# --- Exportliste -------------------------------------------------------------
__all__ = [
    "track_to_scene_end_fn",
    "register",
    "unregister",
    "CLIP_OT_bidirectional_track",
]

# API-Funktionen nur exportieren, wenn vorhanden
if refine_on_high_error is not None:
    __all__.append("refine_on_high_error")
if compute_high_error_frames is not None:
    __all__.append("compute_high_error_frames")


# --- Registrierlisten --------------------------------------------------------
_FIXED_CLASSES = [
    CLIP_OT_bidirectional_track,
]
# Refine-Operator (nur falls in dieser Version vorhanden)
if CLIP_OT_refine_high_error is not None:
    _FIXED_CLASSES.append(CLIP_OT_refine_high_error)

_OPTIONAL_CLASSES = []
if CLIP_OT_optimize_tracking_modal is not None:
    _OPTIONAL_CLASSES.append(CLIP_OT_optimize_tracking_modal)
if CLIP_OT_marker_helper_main is not None:
    _OPTIONAL_CLASSES.append(CLIP_OT_marker_helper_main)


# --- Register/Unregister -----------------------------------------------------
def register() -> None:
    """Registriert feste Operatoren + optionale Operatoren."""
    for cls in _FIXED_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            # bereits registriert → ignorieren
            pass

    for cls in _OPTIONAL_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass


def unregister() -> None:
    # erst optionale, dann feste (Reverse-Reihenfolge)
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
    # refine_on_high_error ist optional
