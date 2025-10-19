# Operator/auto_calibrate_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator
from ..Helper.snapshot import snapshot_active_markers


def _find_track_by_name(tracking: bpy.types.MovieTracking, name: str):
    """Hole Track wahlweise aus active object oder dem root-Set."""
    if getattr(tracking.objects, "active", None):
        tr = tracking.objects.active.tracks.get(name)
        if tr:
            return tr
    return tracking.tracks.get(name)


def _total_length_for_tracks(clip: bpy.types.MovieClip, track_names, start_frame: int = 1) -> int:
    """
    Summiert die Längen (Segmentlogik) über alle angegebenen Tracks.
    Ein Segment ist eine Folge von aufeinanderfolgenden Frames (Lücke > 1 trennt Segmente).
    """
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return 0

    total = 0
    for name in track_names:
        tr = _find_track_by_name(tracking, name)
        if not tr:
            continue

        frames = sorted([mk.frame for mk in tr.markers if mk.frame >= int(start_frame)])
        if not frames:
            continue

        seg_start = frames[0]
        prev = frames[0]
        for f in frames[1:]:
            if f - prev > 1:
                total += (prev - seg_start + 1)
                seg_start = f
            prev = f
        total += (prev - seg_start + 1)

    return int(total)


class KAISERLICHTRACKER_OT_auto_calibrate(Operator):
    """Snapshot -> Detect/Adapt -> Gesamtlänge NEUER Tracks ermitteln."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto Calibrate Tracking (Total Length)"
    bl_options = {"REGISTER", "UNDO"}

    start_frame: bpy.props.IntProperty(  # type: ignore
        name="Start Frame",
        default=1,
        min=0,
        description="Ab diesem Frame wird gezählt"
    )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({"ERROR"}, "Kein aktiver MovieClip im Clip-Editor.")
            return {"CANCELLED"}

        # 1) Baseline-Snapshot: vorhandene Track-Namen
        pre_snapshot = snapshot_active_markers(context)
        baseline_names = {m.get("track") for m in pre_snapshot if m.get("track")}
        self.report({"INFO"}, f"Baseline: {len(baseline_names)} Tracks.")

        # 2) Detect/Adapt (erzeugt neue Marker/Tracks)
        try:
            result = bpy.ops.kaiserlich_tracker.detect_adapt()
        except Exception as ex:
            self.report({"ERROR"}, f"Detect/Adapt Fehler: {ex}")
            return {"CANCELLED"}
        if result not in ({"FINISHED"}, {"CANCELLED"}):
            self.report({"WARNING"}, f"Detect/Adapt Rückgabewert: {result}")

        # 3) neue Tracks seit Baseline
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({"ERROR"}, "Clip hat kein Tracking-Objekt.")
            return {"CANCELLED"}
        all_names = [t.name for t in tracking.tracks]
        new_names = [n for n in all_names if n not in baseline_names]

        # 4) nur EINE Zahl: Gesamtlänge der neuen Tracks
        total_length = _total_length_for_tracks(clip, new_names, start_frame=self.start_frame)

        # optional für UI/Debug
        clip["new_tracks_total_length"] = int(total_length)

        self.report({"INFO"}, f"Gesamtlänge neuer Tracks: {int(total_length)} Frames")
        return {"FINISHED"}
