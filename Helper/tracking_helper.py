# =========================
# File: Helper/tracking_helper.py
# =========================
# SPDX-License-Identifier: GPL-2.0-or-later
"""
Track-Helper: **einziger** Operator `BW_OT_track_to_scene_end` (bl_idname:
"bw.track_to_scene_end").

- Trackt *selektierte* Marker vorwärts (backwards=False) über die Sequenz
  (sequence=True)
- Verwendet `context.temp_override(window, area, region, space_data)` und ruft
  `bpy.ops.clip.track_markers('INVOKE_DEFAULT', ...)` **ohne** Override-Arg auf
  (Fix für "1-2 args execution context is supported").
- Setzt nach dem Tracking den Playhead auf den Ausgangsframe zurück.
- Optionales Feedback an Coordinator via WindowManager-Token.
"""
from __future__ import annotations

from typing import Optional, Dict, Any
import bpy
from bpy.props import BoolProperty, StringProperty

__all__ = ("BW_OT_track_to_scene_end", "register", "unregister")


# ------------------------------------------------------------
# Utility: Clip-Editor-Handles suchen
# ------------------------------------------------------------

def _clip_editor_handles(ctx: bpy.types.Context) -> Optional[Dict[str, Any]]:
    win = ctx.window
    if not win or not win.screen:
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {"window": win, "area": area, "region": region, "space_data": space}
    return None


# ------------------------------------------------------------
# Einziger Operator
# ------------------------------------------------------------
class BW_OT_track_to_scene_end(bpy.types.Operator):
    bl_idname = "bw.track_to_scene_end"
    bl_label = "Track Selected Markers (Forward, Sequence)"
    bl_description = (
        "Trackt selektierte Marker vorwärts über die Sequenz und setzt danach den Playhead zurück."
    )
    bl_options = {"REGISTER", "UNDO"}

    backwards: BoolProperty(name="Backwards", default=False, options={'HIDDEN'})
    sequence: BoolProperty(name="Sequence", default=True, options={'HIDDEN'})
    coord_token: StringProperty(name="Coordinator Token", default="", options={'HIDDEN'})

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Nur aktivieren, wenn ein Clip-Editor offen ist (wir brauchen space_data)
        return _clip_editor_handles(context) is not None

    def invoke(self, context: bpy.types.Context, event):
        return self.execute(context)

    def execute(self, context: bpy.types.Context):
        scene = context.scene
        wm = context.window_manager
        if scene is None:
            self.report({'ERROR'}, "Kein Scene-Kontext verfügbar")
            return {'CANCELLED'}

        handles = _clip_editor_handles(context)
        if not handles:
            self.report({'ERROR'}, "Kein CLIP_EDITOR im aktuellen Window gefunden")
            return {'CANCELLED'}

        start_frame = int(scene.frame_current)
        end_frame = int(scene.frame_end)

        try:
            # Robustes Ausführen innerhalb temp_override
            with context.temp_override(**handles):
                bpy.ops.clip.track_markers(
                    'INVOKE_DEFAULT',
                    backwards=False,   # explizit: nur vorwärts
                    sequence=True,     # über gesamte Sequenz
                )

            tracked_until = int(context.scene.frame_current)
            # Playhead zurücksetzen
            scene.frame_set(start_frame)

            # Rückmeldung an Coordinator (optional)
            if self.coord_token:
                wm["bw_tracking_done_token"] = self.coord_token
            wm["bw_tracking_last_info"] = {
                "start_frame": start_frame,
                "tracked_until": tracked_until,
                "scene_end": end_frame,
                "backwards": False,
                "sequence": True,
            }
            self.report({'INFO'}, "Tracking abgeschlossen; Playhead zurückgesetzt")
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'}, f"Tracking fehlgeschlagen: {ex}")
            return {'CANCELLED'}


# ----------
# Register
# ----------
_classes = (BW_OT_track_to_scene_end,)


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


# =========================
# File: Helper/__init__.py
# =========================
# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/__init__.py – **nur** `BW_OT_track_to_scene_end` wird exportiert und
registriert. Keine Alias-/Legacy-Varianten mehr.
"""
from __future__ import annotations

import bpy
from .tracking_helper import BW_OT_track_to_scene_end

__all__ = ["BW_OT_track_to_scene_end", "register", "unregister"]


def register() -> None:
    try:
        bpy.utils.register_class(BW_OT_track_to_scene_end)
    except ValueError:
        pass
    print("[Helper] register() OK (track_to_scene_end)")


def unregister() -> None:
    try:
        bpy.utils.unregister_class(BW_OT_track_to_scene_end)
    except Exception:
        pass
    print("[Helper] unregister() OK (track_to_scene_end)")
