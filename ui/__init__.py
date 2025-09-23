# SPDX-License-Identifier: GPL-2.0-or-later
"""UI stub – Grafik-Overlay wurde vollständig entfernt."""

# UI-Paket (klein geschrieben). Registriert Panels + UI-Scene-Properties.
import bpy
from bpy.props import BoolProperty, FloatProperty

from .panel_main import CLIP_PT_kaiserlich_panel

_UI_CLASSES = [
    CLIP_PT_kaiserlich_panel,
]

def register():
    # UI-Properties (Focal-Steuerung)
    bpy.types.Scene.tco_use_auto_focal = BoolProperty(
        name="Auto-Brennweite (Refine)",
        description="Wenn aktiv, wird die Brennweite automatisch bestimmt; "
                    "die 10%-Klammer wird aufgehoben.",
        default=True,
    )
    bpy.types.Scene.tco_focal_override = FloatProperty(
        name="Fixe Brennweite (mm)",
        description="Wenn Auto-Brennweite aus ist, wird dieser Wert als fixe Brennweite verwendet.",
        default=35.0,
        min=0.1,
        max=5000.0,
        precision=3,
    )
    for c in _UI_CLASSES:
        try:
            bpy.utils.register_class(c)
        except Exception:
            pass

def unregister():
    for c in reversed(_UI_CLASSES):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "tco_use_auto_focal"):
        del bpy.types.Scene.tco_use_auto_focal
    if hasattr(bpy.types.Scene, "tco_focal_override"):
        del bpy.types.Scene.tco_focal_override
