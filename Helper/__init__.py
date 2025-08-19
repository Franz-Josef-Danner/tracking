# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/__init__.py (Minimal-Registrar + optionale Operatoren)

- Registriert immer den simplen Track-Helper aus `tracking_helper.py`
  (`BW_OT_track_simple_forward`).
- Registriert zusätzlich – falls vorhanden –
  `CLIP_OT_optimize_tracking_modal` und `CLIP_OT_marker_helper_main`.
- Robuste Imports: optionale Module werden per try/except geladen,
  damit das Add-on auch ohne sie aktivierbar ist.
"""
from __future__ import annotations

import bpy

# WICHTIG: Den **Alias-Operator** importieren, nicht per "as" umbenennen,
# damit bl_idname == 'bw.track_simple_forward' bleibt.
from .tracking_helper import BW_OT_track_simple_forward  # noqa: F401


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
    "BW_OT_track_simple_forward",
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


# --- Kern-Registrierung für den einfachen Track-Operator ---

def _reg_impl() -> None:
    try:
        bpy.utils.register_class(BW_OT_track_simple_forward)
    except ValueError:
        # Bereits registriert → ok
        pass


def _unreg_impl() -> None:
    try:
        bpy.utils.unregister_class(BW_OT_track_simple_forward)
    except Exception:
        pass


def register() -> None:
    """Registriert den simplen Track-Helper + optionale Operatoren."""
    # 1) Kern-Helper registrieren (stellt bw.track_simple_forward bereit)
    _reg_impl()
    # 2) Optionale Operatoren – nur wenn vorhanden
    for cls in _optional_classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            # Bereits registriert
            pass
    print("[Helper] register() OK")


def unregister() -> None:
    """Hebt die Registrierung optionaler Operatoren und des Kern-Helpers auf."""
    for cls in reversed(_optional_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _unreg_impl()
    print("[Helper] unregister() OK")


if __name__ == "__main__":
    # Leichter Sanity-Check ohne UI/Operator-Aufruf
    assert hasattr(BW_OT_track_simple_forward, 'bl_idname')
    assert BW_OT_track_simple_forward.bl_idname == 'bw.track_simple_forward'
