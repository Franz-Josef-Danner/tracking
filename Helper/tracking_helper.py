# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/tracking_helper.py (MINIMAL)

Ein **schlanker** Track‑Helper, der *nur* den bestehenden Blender‑Operator
aufruft:

    bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)

Voraussetzungen:
- Du hast im **Clip Editor** bereits den gewünschten Clip offen.
- Die **Marker/Tracks sind bereits selektiert** (der Helper nimmt keine Auto‑Selektion vor).

Bereitgestellt:
- Operator: `bw.track_simple_forward`
- Funktion: `helper_track_forward_sequence_invoke_default()`

Hinweis Blender 4.x: Aufrufe erfolgen mit `context.temp_override(**ctx)` (kein
positional Override‑Dict), um den Fehler "1-2 args execution context is supported"
zu vermeiden.
"""
from __future__ import annotations

import bpy
from bpy.types import Operator

__all__ = (
    "BW_OT_track_simple_forward",
    "helper_track_forward_sequence_invoke_default",
    "register",
    "unregister",
)


# ------------------------------------------------------------
# Kontext-Helfer (nur was für temp_override nötig ist)
# ------------------------------------------------------------

def _find_clip_context_full(context: bpy.types.Context) -> dict:
    win = getattr(context, "window", None)
    scr = getattr(win, "screen", None) if win else None
    if not (win and scr):
        raise RuntimeError("Kein aktives Fenster/Screen verfügbar.")

    for area in scr.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {
                        'window': win,
                        'screen': scr,
                        'area': area,
                        'region': region,
                        'space_data': area.spaces.active,
                        'scene': context.scene,
                    }
    raise RuntimeError("Kein CLIP_EDITOR mit WINDOW-Region im aktuellen UI-Layout gefunden.")


def _has_selected_tracks(override: dict) -> bool:
    space = override.get('space_data')
    clip = getattr(space, 'clip', None) if space else None
    if not clip:
        return False
    return any(t.select for t in clip.tracking.tracks)


# ------------------------------------------------------------
# Öffentliche Helper-Funktion
# ------------------------------------------------------------

def helper_track_forward_sequence_invoke_default() -> None:
    """UI‑konformer Aufruf des eingebauten Track‑Operators (vorwärts, Sequenz)."""
    ctx = _find_clip_context_full(bpy.context)
    if not _has_selected_tracks(ctx):
        raise RuntimeError("Keine selektierten Tracks im aktiven Clip.")
    with bpy.context.temp_override(**ctx):
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)


# ------------------------------------------------------------
# Minimaler Operator (nur Trigger)
# ------------------------------------------------------------

class BW_OT_track_simple_forward(Operator):
    """Löst `track_markers` mit INVOKE_DEFAULT, forwards, sequence=True aus."""

    bl_idname = "bw.track_simple_forward"
    bl_label = "Track Forwards (Sequence, Invoke)"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == 'CLIP_EDITOR')

    def invoke(self, context: bpy.types.Context, _event):
        try:
            ctx = _find_clip_context_full(context)
            if not _has_selected_tracks(ctx):
                self.report({'ERROR'}, "Keine selektierten Tracks im aktiven Clip.")
                return {'CANCELLED'}
            with bpy.context.temp_override(**ctx):
                bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'}, f"Track-Helper-Fehler: {ex}")
            return {'CANCELLED'}

    def execute(self, context: bpy.types.Context):
        return self.invoke(context, None)


# ------------------------------------------------------------
# Registrierung
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(BW_OT_track_simple_forward)


def unregister():
    bpy.utils.unregister_class(BW_OT_track_simple_forward)


# ------------------------------------------------------------
# Kleine Self‑Tests (ohne UI‑Aktion)
# ------------------------------------------------------------

def _selftest():
    assert BW_OT_track_simple_forward.bl_idname == 'bw.track_simple_forward'


if __name__ == "__main__":
    _selftest()
