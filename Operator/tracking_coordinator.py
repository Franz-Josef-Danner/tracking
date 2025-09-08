"""tracking_coordinator.py – Minimal: Delegiert ausschließlich an Helper/distanze.run_distance_cleanup."""
from __future__ import annotations
import bpy
from typing import Optional, Set

# Einziger fachlicher Import: Distanz-Cleanup.
from ..Helper.distanze import run_distance_cleanup

__all__ = ("CLIP_OT_tracking_coordinator",)


def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Sucht den aktiven Clip (Editor, Scene, Fallback: erstes MovieClip)."""
    scn = getattr(context, "scene", None)
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        space = getattr(context, "space_data", None)
        if space and getattr(space, "type", None) == "CLIP_EDITOR":
            clip = getattr(space, "clip", None)
    if not clip and scn:
        clip = getattr(scn, "clip", None)
    if not clip:
        try:
            # Letzter Fallback: irgendein Clip in der Datei
            clip = next(iter(bpy.data.movieclips))
        except Exception:
            clip = None
    return clip


def _collect_pre_ptrs(context: bpy.types.Context, frame: int, *, include_muted_old: bool = False) -> Set[int]:
    """
    Ermittelt die 'alten' Tracks am Frame: alle Tracks, die am angegebenen Frame
    bereits einen Marker besitzen. Muted-Marker werden optional ausgeschlossen.
    """
    clip = _resolve_clip(context)
    if not clip:
        return set()

    pre_ptrs: Set[int] = set()
    for tr in getattr(clip.tracking, "tracks", []):
        try:
            try:
                m = tr.markers.find_frame(int(frame), exact=True)
            except TypeError:
                m = tr.markers.find_frame(int(frame))
            if not m:
                continue
            if not include_muted_old and (getattr(m, "mute", False) or getattr(tr, "mute", False)):
                continue
            pre_ptrs.add(int(tr.as_pointer()))
        except Exception:
            # Defensive: einzelne Fehler ignorieren, restliche Tracks weiter prüfen
            continue
    return pre_ptrs


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """
    Kaiserlich: Coordinator (DISTANZE-Only)
    Führt KEINE Detect/Count-Abläufe mehr aus, sondern ruft ausschließlich
    Helper/distanze.run_distance_cleanup(...) auf dem aktuellen Frame auf.
    """
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator (Distanz-Cleanup)"
    bl_options = {"REGISTER", "UNDO"}

    # Optional: einfache Properties, falls später parametrierbar gewünscht.
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
        description="<=0: auto aus Detection-Threshold ableiten; >0: fixer Mindestabstand",
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
        clip = _resolve_clip(context)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        scn = context.scene
        frame = int(getattr(scn, "frame_current", getattr(scn, "frame_start", 1)))

        # 1) Alte Tracks am aktuellen Frame ermitteln
        pre_ptrs = _collect_pre_ptrs(context, frame, include_muted_old=self.include_muted_old)

        # 2) Direkt an Distanz-Cleanup delegieren (Auto-Abstand, wenn ≤0)
        try:
            md = None if self.min_distance <= 0.0 else float(self.min_distance)
            res = run_distance_cleanup(
                context,
                pre_ptrs=pre_ptrs,
                frame=frame,
                min_distance=md,
                distance_unit=self.distance_unit,
                require_selected_new=self.require_selected_new,
                include_muted_old=self.include_muted_old,
                select_remaining_new=self.select_remaining_new,
                verbose=self.verbose,
            )
        except Exception as exc:
            self.report({'ERROR'}, f"Distanz-Cleanup fehlgeschlagen: {exc}")
            return {'CANCELLED'}

        # 3) UI-Feedback
        status = str(res.get("status", "FAILED"))
        if status != "OK":
            self.report({'WARNING'}, f"Distanz-Cleanup Status: {status} (Frame {frame})")
            return {'CANCELLED'}

        removed = int(res.get("removed", 0))
        kept = int(res.get("kept", 0))
        self.report({'INFO'}, f"Distanz-Cleanup @f{frame}: removed={removed}, kept={kept}")
        return {'FINISHED'}
