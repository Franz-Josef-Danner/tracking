# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/__init__.py – Function-only Registrar (mit optionalen Operatoren)

- **Kein** Track-Operator mehr – stattdessen Funktions-API:
    from .tracking_helper import track_to_scene_end_fn
- `register()`/`unregister()` registrieren nur **optionale** weitere Operatoren,
  die es evtl. in deinem Projekt gibt (optimize, marker_helper_main).
- Kompatibel mit Top-Level-Aufrufern, die `Helper.register()` erwarten.
"""
from __future__ import annotations

import bpy

# Funktions-API (einziger fester Export)
from .tracking_helper import track_to_scene_end_fn  # noqa: F401

# Optional 1: Optimize-Operator (falls Modul existiert)
try:
    from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal  # type: ignore
except Exception:
    CLIP_OT_optimize_tracking_modal = None  # type: ignore

# Optional 2: Marker-Helper-Main (falls Modul existiert)
try:
    from .marker_helper_main import CLIP_OT_marker_helper_main  # type: ignore
except Exception:
    CLIP_OT_marker_helper_main = None  # type: ignore


__all__ = [
    "track_to_scene_end_fn",
    "register",
    "unregister",
]
if CLIP_OT_optimize_tracking_modal is not None:
    __all__.append("CLIP_OT_optimize_tracking_modal")
if CLIP_OT_marker_helper_main is not None:
    __all__.append("CLIP_OT_marker_helper_main")


# Sammle optionale Klassen
_optional_classes = []
if CLIP_OT_optimize_tracking_modal is not None:
    _optional_classes.append(CLIP_OT_optimize_tracking_modal)
if CLIP_OT_marker_helper_main is not None:
    _optional_classes.append(CLIP_OT_marker_helper_main)


def register() -> None:
    """Registriert **nur** optionale Operatoren. Die Helper-Funktion benötigt
    keine Registrierung."""
    for cls in _optional_classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass
    print("[Helper] register() OK (function-only; optional ops registered)")


def unregister() -> None:
    for cls in reversed(_optional_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    print("[Helper] unregister() OK (function-only; optional ops unregistered)")


if __name__ == "__main__":
    # Sanity-Check: Funktions-API vorhanden
    assert callable(track_to_scene_end_fn)
