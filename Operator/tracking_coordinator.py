"""tracking_coordinator.py – Reduzierte Variante
Fokus: distanze.py isoliert entwickeln ⇒ Pipeline endet nach DETECT.
Ablauf: FIND_LOW → JUMP → DETECT → ENDE (kein Distanz-Cleanup, kein Solve, kein Bidi)."""
from __future__ import annotations
import bpy

# --- Imports: nur das Nötigste für Detect-only ---
from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame
from ..Helper.detect import run_detect_once
from ..Helper.tracker_settings import apply_tracker_settings

__all__ = ("CLIP_OT_tracking_coordinator",)

def _resolve_clip(context: bpy.types.Context):
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip

def _reset_margin_to_tracker_default(context: bpy.types.Context) -> None:
    """Setzt default_margin deterministisch zurück (Search-Size-Baseline)."""
    try:
        clip = _resolve_clip(context)
        tr = getattr(clip, "tracking", None) if clip else None
        settings = getattr(tr, "settings", None) if tr else None
        if not settings:
            return
        # prefer gespeicherte Tracker-Settings
        scn = context.scene
        base_margin = None
        try:
            scn["tco_last_tracker_settings"] = dict(apply_tracker_settings(context, scene=scn, log=False))
            base_margin = int(scn["tco_last_tracker_settings"].get("search_size", 0)) or None
        except Exception:
            base_margin = None
        if base_margin is None and clip and getattr(clip, "size", None):
            width = int(clip.size[0])
            pattern = max(1, int(width / 100)) if width > 0 else 8
            base_margin = pattern * 2
        if base_margin is not None:
            settings.default_margin = int(base_margin)
    except Exception:
        pass

class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Coordinator (Detect-only)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator (Detect-only)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # 1) Low-Marker-Frame bestimmen
        try:
            frame = int(run_find_low_marker_frame(context))
        except Exception:
            frame = None
        if frame is None:
            self.report({'WARNING'}, "Kein Low-Marker-Frame gefunden.")
            return {'CANCELLED'}

        # 2) Springen
        try:
            run_jump_to_frame(context, frame=frame)
        except Exception as exc:
            self.report({'ERROR'}, f"Jump fehlgeschlagen: {exc}")
            return {'CANCELLED'}

        # 3) Einmalige Detection
        try:
            res = run_detect_once(context, start_frame=frame)
        except Exception as exc:
            self.report({'ERROR'}, f"Detect fehlgeschlagen: {exc}")
            return {'CANCELLED'}

        # 4) Aufräumen der Margin-Defaults (keine weiteren Phasen)
        _reset_margin_to_tracker_default(context)

        cnt = int(res.get("new_count", -1)) if isinstance(res, dict) else -1
        self.report({'INFO'}, f"Detect abgeschlossen @f{frame} (neu: {cnt if cnt>=0 else 'n/a'})")
        return {'FINISHED'}
