# Operator/auto_calibrate_operator.py

import bpy
from typing import Iterable

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names
from ..Helper.playhead_helper import get_start_frame, reset_to_frame

# ---- Utility ---------------------------------------------------------------

def set_all_thresholds_to_one(context: bpy.types.Context) -> None:
    scene = context.scene
    props: Iterable[str] = (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    )
    for p in props:
        if hasattr(scene, p):
            try:
                setattr(scene, p, 1.0)
            except Exception:
                pass  # fail-soft


def _call_get_start_frame(context=None):
    try:
        return get_start_frame(context) if context is not None else get_start_frame()
    except TypeError:
        return get_start_frame()


def _call_reset_to_frame(frame, context=None):
    try:
        return reset_to_frame(context, frame) if context is not None else reset_to_frame(frame)
    except TypeError:
        return reset_to_frame(frame)


def auto_calibrate_pipeline(context=None, tracks_to_delete=None):
    """
    Reihenfolge:
      0) set_all_thresholds_to_one
      1) snapshot_active_markers
      2) bpy.ops.kaiserlich_tracker.detect_adapt
      2.5) get_start_frame        <-- NEU (vor Tracking)
      3) bpy.ops.kaiserlich_tracker.track_cycle
      4) get_total_track_length
      5) delete_tracks_by_names   (optional)
      6) reset_to_frame(start)    <-- NEU (am Ende/immer)
    """
    start_frame = None
    try:
        # 0) Thresholds
        if context is not None:
            try:
                set_all_thresholds_to_one(context)
            except Exception:
                pass

        # 1) Snapshot
        try:
            (snapshot_active_markers(context) if context is not None else snapshot_active_markers())
        except TypeError:
            snapshot_active_markers()

        # 2) Detect-Adapt
        result = bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Detect-Adapt wurde abgebrochen.")

        # 2.5) Start-Frame sichern (vor Tracking)
        start_frame = _call_get_start_frame(context)

        # 3) Track Cycle
        result = bpy.ops.kaiserlich_tracker.track_cycle('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Tracking Cycle wurde abgebrochen.")

        # 4) Track-Länge
        try:
            total_len = get_total_track_length(context) if context is not None else get_total_track_length()
        except TypeError:
            total_len = get_total_track_length()

        # 5) Optionales Cleanup
        deleted = []
        if tracks_to_delete:
            names = [n.strip() for n in tracks_to_delete if n and n.strip()]
            if names:
                try:
                    (delete_tracks_by_names(context, names) if context is not None else delete_tracks_by_names(names))
                except TypeError:
                    delete_tracks_by_names(names)
                deleted = names

        return {"total_track_length": total_len, "deleted": deleted, "start_frame": start_frame}

    finally:
        # 6) Playhead zurücksetzen – auch bei Exceptions, sofern Start bekannt
        if start_frame is not None:
            try:
                _call_reset_to_frame(start_frame, context)
            except Exception:
                # Fail-soft: kein Hard-Abbruch, falls Reset scheitert
                pass
# ---- Operator ------------------------------------------------

import bpy

from ..Utility.auto_calibrate import auto_calibrate_pipeline, set_all_thresholds_to_one


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: initialisiert alle Ziel-Parameter auf 1 und führt danach Detect-Adapt und Tracking aus."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    tracks_to_delete: bpy.props.StringProperty(
        name="Tracks to delete (comma-separated)",
        default="",
        description="Optional: Namen der zu löschenden Tracks, getrennt durch Kommas"
    )

    def execute(self, context):
        try:
            # proaktives UI-Feedback (Utility setzt trotzdem selbst ⇒ idempotent)
            set_all_thresholds_to_one(context)
            self.report({'INFO'}, "KaiserlichTracker: Thresholds => 1.0")

            names = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
            result = auto_calibrate_pipeline(context=context, tracks_to_delete=names)

            self.report({'INFO'}, f"Auto-Calibrate abgeschlossen. Track-Länge gesamt: {result.get('total_track_length')}")
            if result.get("deleted"):
                self.report({'INFO'}, f"Gelöschte Tracks: {', '.join(result['deleted'])}")
            if result.get("start_frame") is not None:
                self.report({'INFO'}, f"Playhead zurückgesetzt auf Frame {result['start_frame']}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Auto-Calibrate fehlgeschlagen: {e}")
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
