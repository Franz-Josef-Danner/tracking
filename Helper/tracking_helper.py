# File: Helper/tracking_helper.py
# SPDX-License-Identifier: GPL-2.0-or-later
"""
Track-Helper: trackt **selektierte Marker** mit INVOKE_DEFAULT, backwards=False,
sequence=True, setzt danach den Playhead zurück und meldet Abschluss via
WindowManager-Token an den Coordinator.

WICHTIG (Fix für ImportError):
Dieses Modul exportiert **zwei** Operator-Klassen:
- `BW_OT_track_to_scene_end`  (bl_idname: "bw.track_to_scene_end")
- `BW_OT_track_simple_forward` (Alias-Klasse für Legacy-Imports; bl_idname: "bw.track_simple_forward")

Damit funktionieren beide Varianten deiner bestehenden Imports/Coordinators.
"""
from __future__ import annotations

from typing import Optional, Dict, Any
import bpy
from bpy.props import BoolProperty, StringProperty

__all__ = (
    "BW_OT_track_to_scene_end",
    "BW_OT_track_simple_forward",
    "register",
    "unregister",
)


# ------------------------------------------------------------
# Utility: Clip-Editor-Override finden
# ------------------------------------------------------------

def _clip_editor_override(ctx: bpy.types.Context) -> Optional[Dict[str, Any]]:
    win = ctx.window
    if not win:
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            reg = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if reg:
                return {"window": win, "screen": win.screen, "area": area, "region": reg}
    return None


# ------------------------------------------------------------
# Haupt-Operator
# ------------------------------------------------------------
class BW_OT_track_to_scene_end(bpy.types.Operator):
    bl_idname = "bw.track_to_scene_end"
    bl_label = "Track Selected Markers (Forward, Sequence)"
    bl_description = (
        "Trackt selektierte Marker vorwärts über die Sequenz und setzt danach den Playhead zurück."
    )
    bl_options = {"REGISTER", "UNDO"}

    backwards: BoolProperty(
        name="Backwards",
        default=False,
        description="Nur Vorwärts-Tracking (wie angefordert)",
        options={'HIDDEN'},
    )
    sequence: BoolProperty(
        name="Sequence",
        default=True,
        description="Über die ganze Sequenz weitertracken",
        options={'HIDDEN'},
    )
    coord_token: StringProperty(
        name="Coordinator Token",
        default="",
        description="Token zur Synchronisation mit dem Coordinator",
        options={'HIDDEN'},
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Idealerweise im Clip-Editor, aber wir erlauben Execute mit Override
        return True

    def invoke(self, context: bpy.types.Context, event):
        return self.execute(context)

    def execute(self, context: bpy.types.Context):
        scene = context.scene
        wm = context.window_manager
        if scene is None:
            self.report({'ERROR'}, "Kein Scene-Kontext verfügbar")
            return {'CANCELLED'}

        orig_frame = int(scene.frame_current)

        # Clip-Editor-Override aufbauen
        override = _clip_editor_override(context)
        if override is None:
            self.report({'ERROR'}, "Kein CLIP_EDITOR im aktuellen Window gefunden")
            return {'CANCELLED'}

        try:
            end_frame = int(scene.frame_end)

            # Tracking: selektierte Marker, vorwärts, sequence=True
            bpy.ops.clip.track_markers(
                override,
                'EXEC_DEFAULT',
                backwards=bool(self.backwards),
                sequence=bool(self.sequence),
            )

            # Nach dem Tracking Playhead zurücksetzen
            tracked_until = int(context.scene.frame_current)
            scene.frame_set(orig_frame)

            # Rückmeldung an Coordinator
            if self.coord_token:
                wm["bw_tracking_done_token"] = self.coord_token
            wm["bw_tracking_last_info"] = {
                "start_frame": orig_frame,
                "tracked_until": tracked_until,
                "scene_end": end_frame,
                "backwards": bool(self.backwards),
                "sequence": bool(self.sequence),
            }
            self.report({'INFO'}, "Tracking abgeschlossen; Playhead zurückgesetzt")
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'}, f"Tracking fehlgeschlagen: {ex}")
            return {'CANCELLED'}


# ------------------------------------------------------------
# Alias-Operator (Legacy-Name)
# ------------------------------------------------------------
class BW_OT_track_simple_forward(BW_OT_track_to_scene_end):
    """Alias zu BW_OT_track_to_scene_end.

    Diese Klasse existiert nur, damit bestehende Imports wie
    `from .tracking_helper import BW_OT_track_simple_forward` funktionieren.
    """

    bl_idname = "bw.track_simple_forward"
    bl_label = "Track Selected Markers (Simple Forward)"

    # Defaults sicherstellen (bereitgestellt durch Basisklasse):
    # backwards=False, sequence=True


# ----------
# Register
# ----------
_classes = (
    BW_OT_track_to_scene_end,
    BW_OT_track_simple_forward,
)


def register():
    for c in _classes:
        try:
            bpy.utils.register_class(c)
        except ValueError:
            pass


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
