"""tracking_coordinator.py – Ultra-Minimal: genau EIN Call in den Distanz-Helper."""
from __future__ import annotations
import bpy
from typing import Optional
from ..Helper.distanze import run_distance_cleanup

__all__ = ("CLIP_OT_tracking_coordinator",)


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Coordinator → Distanz (Single Call)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator (Distanz)"
    bl_options = {"REGISTER", "UNDO"}

    require_selected_new: bpy.props.BoolProperty(  # type: ignore[attr-defined]
        name="Nur selektierte neue Marker",
        default=True,
        description="Nur neu gesetzte, selektierte Marker am Frame bereinigen",
    )
    include_muted_old: bpy.props.BoolProperty(  # type: ignore[attr-defined]
        name="Gemutete alte Marker berücksichtigen",
        default=False,
        description="Auch gemutete Alt-Marker als Referenz zulassen",
    )
    distance_unit: bpy.props.EnumProperty(  # type: ignore[attr-defined]
        name="Distanz-Einheit",
        items=[("pixel", "Pixel", ""), ("normalized", "Normalized", "")],
        default="pixel",
    )
    min_distance: bpy.props.FloatProperty(  # type: ignore[attr-defined]
        name="Mindestabstand",
        default=-1.0,
        min=-1.0,
        description="<=0: auto; >0: fixer Mindestabstand",
    )
    select_remaining_new: bpy.props.BoolProperty(  # type: ignore[attr-defined]
        name="Verbleibende neue selektieren",
        default=True,
        description="Nach Cleanup verbleibende neue Marker selektieren",
    )
    verbose: bpy.props.BoolProperty(  # type: ignore[attr-defined]
        name="Verbose",
        default=True,
        description="Konsolen-Logs des Distanz-Helpers an",
    )

    def execute(self, context):
        scn = context.scene
        frame = int(getattr(scn, "frame_current", getattr(scn, "frame_start", 1)))
        try:
            res = run_distance_cleanup(
                context,
                frame=frame,
                min_distance=(None if self.min_distance <= 0.0 else float(self.min_distance)),
                distance_unit=self.distance_unit,
                require_selected_new=self.require_selected_new,
                include_muted_old=self.include_muted_old,
                select_remaining_new=self.select_remaining_new,
                verbose=self.verbose,
            )  # **Einziger Aufruf**
        except Exception as exc:
            self.report({'ERROR'}, f"Distanz-Cleanup fehlgeschlagen: {exc}")
            return {'CANCELLED'}

        status = str(res.get("status", "FAILED"))
        if status != "OK":
            self.report({'WARNING'}, f"Distanz-Cleanup Status: {status} (Frame {frame})")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Distanz-Cleanup @f{frame}: removed={int(res.get('removed',0))}, kept={int(res.get('kept',0))}")
        return {'FINISHED'}

