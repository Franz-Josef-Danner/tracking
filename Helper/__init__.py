# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/__init__.py – Function + Operator Registrar

- Exportiert Funktions-API (z. B. track_to_scene_end_fn).
- Registriert **immer** den Bidirectional-Operator,
  sowie optionale weitere Operatoren (optimize, marker_helper_main).
"""

from __future__ import annotations
import bpy

# Funktions-API
from .tracking_helper import track_to_scene_end_fn  # noqa: F401

# Fester Operator: Bidirectional Track
from .bidirectional_track import CLIP_OT_bidirectional_track

# Optionale Operatoren
try:
    from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal  # type: ignore
except Exception:
    CLIP_OT_optimize_tracking_modal = None  # type: ignore

try:
    from .marker_helper_main import CLIP_OT_marker_helper_main  # type: ignore
except Exception:
    CLIP_OT_marker_helper_main = None  # type: ignore


__all__ = [
    "track_to_scene_end_fn",
    "register",
    "unregister",
    "CLIP_OT_bidirectional_track",
]

_optional_classes = []
if CLIP_OT_optimize_tracking_modal is not None:
    _optional_classes.append(CLIP_OT_optimize_tracking_modal)
if CLIP_OT_marker_helper_main is not None:
    _optional_classes.append(CLIP_OT_marker_helper_main)


def register() -> None:
    """Registriert Bidirectional-Operator + optionale Operatoren."""
    try:
        bpy.utils.register_class(CLIP_OT_bidirectional_track)
    except ValueError:
        pass

    for cls in _optional_classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass

    print("[Helper] register() OK (bidirectional + optional ops registered)")


def unregister() -> None:
    for cls in reversed(_optional_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    try:
        bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
    except Exception:
        pass

    print("[Helper] unregister() OK (bidirectional + optional ops unregistered)")


if __name__ == "__main__":
    assert callable(track_to_scene_end_fn)
