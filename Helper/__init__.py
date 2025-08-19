# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/__init__.py (Single-Operator Registrar)

- Registriert **nur** den Track-Helper `BW_OT_track_to_scene_end` aus
  `tracking_helper.py` (bl_idname: `bw.track_to_scene_end`).
- Optionale Operatoren (`CLIP_OT_optimize_tracking_modal`,
  `CLIP_OT_marker_helper_main`) werden best-effort geladen/registriert.
- Keine Alias-/Legacy-Namen mehr.
"""
from __future__ import annotations

import bpy

# Fester Bestandteil: einziger Track-Helper
from .tracking_helper import BW_OT_track_to_scene_end  # noqa: F401

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


# Public API
__all__ = [
    "BW_OT_track_to_scene_end",
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


# --- Kern-Registrierung ------------------------------------------------------

def _reg_impl() -> None:
    try:
        bpy.utils.register_class(BW_OT_track_to_scene_end)
    except ValueError:
        # Bereits registriert → ok
        pass


def _unreg_impl() -> None:
    try:
        bpy.utils.unregister_class(BW_OT_track_to_scene_end)
    except Exception:
        pass


def register() -> None:
    """Registriert den Track-Helper + optionale Operatoren."""
    # 1) Kern-Helper registrieren (stellt bw.track_to_scene_end bereit)
    _reg_impl()
    # 2) Optionale Operatoren – nur wenn vorhanden
    for cls in _optional_classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            # Bereits registriert
            pass
    print("[Helper] register() OK (track_to_scene_end)")


def unregister() -> None:
    """Hebt die Registrierung optionaler Operatoren und des Kern-Helpers auf."""
    for cls in reversed(_optional_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _unreg_impl()
    print("[Helper] unregister() OK (track_to_scene_end)")


if __name__ == "__main__":
    # Sanity-Check
    assert hasattr(BW_OT_track_to_scene_end, 'bl_idname')
    assert BW_OT_track_to_scene_end.bl_idname == 'bw.track_to_scene_end'
