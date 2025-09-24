
from __future__ import annotations
# SPDX-License-Identifier: GPL-2.0-or-later
from .Helper.metrics_provider import set_metrics_provider
from .Helper.metrics_provider_blender import BlenderMetricsProvider

bl_info = {
    "name": "Kaiserlich Tracking (KI)",
    "author": "Franz-Josef Danner & Contributors",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "Movie Clip Editor > Sidebar > Kaiserlich",
    "description": "Experimenteller Autotrack-Workflow (STRM, Autotune, Staged Seeding, Online-Loop)",
    "warning": "Experimental",
    "doc_url": "",
    "tracker_url": "",
    "category": "Tracking",
}

import bpy
from bpy.props import IntProperty, FloatProperty

# Submodule-Handles (lazy import in register)
_ui_mod = None
_op_mod = None


def _sync_error_props(self, context):
    scn = context.scene
    # Halte resolve_error und error_track im Gleichlauf
    val = getattr(scn, "error_track", None)
    if val is not None:
        try:
            scn.resolve_error = float(val)
        except Exception:
            pass


def register():
    global _ui_mod, _op_mod

    # Scene-Properties (werden im UI-Panel verwendet)
    bpy.types.Scene.marker_frame = IntProperty(
        name="Marker pro Frame",
        description="Ziel-Marker pro Frame (Basis)",
        default=25,
        min=1,
        soft_max=200,
    )
    bpy.types.Scene.frames_track = IntProperty(
        name="Track-Länge (Frames)",
        description="Ziel-Tracklänge für Micro-Validation / Heuristiken",
        default=25,
        min=1,
        soft_max=5000,
    )
    bpy.types.Scene.resolve_error = FloatProperty(
        name="Solve-Grenze (px)",
        description="Erlaubter Fehler für Solve/Refine (px)",
        default=2.0,
        min=0.0,
        soft_max=10.0,
        precision=3,
    )
    bpy.types.Scene.error_track = FloatProperty(
        name="Fehler-Grenze (px)",
        description="Alias für Solve-Grenze (px) – wird mit resolve_error synchronisiert",
        default=2.0,
        min=0.0,
        soft_max=10.0,
        precision=3,
        update=_sync_error_props,
    )

    # UI registrieren
    from . import ui as _ui
    _ui_mod = _ui
    try:
        _ui_mod.register()
    except Exception:
        pass

    # Operatoren registrieren
    from . import Operator as _op
    _op_mod = _op
    try:
        _op_mod.register()
    except Exception:
        pass

    # Metrics Provider: set default Blender provider regardless of Operator registration outcome
    try:
        set_metrics_provider(BlenderMetricsProvider())
    except Exception:
        # If setting provider fails for any reason, ignore — some functionality will fall back to synthetic metrics
        pass


def unregister():
    global _ui_mod, _op_mod

    if _op_mod:
        try:
            _op_mod.unregister()
        except Exception:
            pass
        _op_mod = None

    if _ui_mod:
        try:
            _ui_mod.unregister()
        except Exception:
            pass
        _ui_mod = None

    # Properties entfernen (falls vorhanden)
    for attr in ("error_track", "resolve_error", "frames_track", "marker_frame"):
        if hasattr(bpy.types.Scene, attr):
            try:
                delattr(bpy.types.Scene, attr)
            except Exception:
                pass
