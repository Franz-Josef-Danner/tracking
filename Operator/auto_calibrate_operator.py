# Operator/auto_calibrate_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator

from ..Helper.snapshot import snapshot_active_markers
from ..Helper import delete as delete_helper
from ..Helper import reset_helper
from ..Operator import detect_adapt_operator, track_operator


def _find_track_by_name(tracking: bpy.types.MovieTracking, name: str):
    if getattr(tracking.objects, "active", None):
        tr = tracking.objects.active.tracks.get(name)
        if tr:
            return tr
    return tracking.tracks.get(name)


def _total_length_for_tracks(clip: bpy.types.MovieClip, track_names, start_frame: int = 1) -> int:
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return 0
    total = 0
    for name in track_names:
        tr = _find_track_by_name(tracking, name)
        if not tr:
            continue
        frames = sorted(mk.frame for mk in tr.markers if mk.frame >= int(start_frame))
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


def _safe_run_detect_adapt(context) -> bool:
    for name in ("run_detect_and_adapt", "run", "main", "execute"):
        fn = getattr(detect_adapt_operator, name, None)
        if callable(fn):
            try:
                fn(context)
                return True
            except Exception as ex:
                print(f"[auto_calibrate] detect_adapt_operator.{name} failed: {ex}")
    try:
        return bpy.ops.kaiserlich_tracker.detect_adapt() == {"FINISHED"}
    except Exception as ex:
        print(f"[auto_calibrate] bpy.ops detect_adapt failed: {ex}")
        return False


def _safe_run_tracking(context) -> bool:
    for name in ("track_cycle", "run", "main", "execute"):
        fn = getattr(track_operator, name, None)
        if callable(fn):
            try:
                fn(context)
                return True
            except TypeError:
                try:
                    fn(context, max_frames=0)
                    return True
                except Exception as ex:
                    print(f"[auto_calibrate] track_operator.{name}(context, max_frames=0) failed: {ex}")
            except Exception as ex:
                print(f"[auto_calibrate] track_operator.{name} failed: {ex}")
    try:
        return bpy.ops.kaiserlich_tracker.track() == {"FINISHED"}
    except Exception as ex:
        print(f"[auto_calibrate] bpy.ops track failed: {ex}")
        return False


def _safe_delete_tracks(context, names: set[str]) -> int:
    for candidate in ("delete_tracks_by_names", "delete_tracks", "remove_tracks_by_name"):
        func = getattr(delete_helper, candidate, None)
        if callable(func):
            try:
                return int(func(context, list(names)))
            except Exception as ex:
                print(f"[auto_calibrate] delete_helper.{candidate} failed: {ex}")

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return 0
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return 0

    removed = 0
    collections = []
    if getattr(tracking.objects, "active", None):
        collections.append(tracking.objects.active.tracks)
    collections.append(tracking.tracks)

    for tracks in collections:
        for tr in list(tracks):
            if tr.name in names:
                try:
                    tracks.remove(tr)
                    removed += 1
                except Exception as ex:
                    print(f"[auto_calibrate] removing track '{tr.name}' failed: {ex}")
    return removed


def _safe_reset(context) -> bool:
    """
    Stelle die Szene wieder her. Versucht bekannte reset_helper-APIs,
    z. B. reset_scene(), reset_all(), restore_initial_state().
    """
    for name in ("reset_scene", "reset_all", "restore_initial_state", "reset"):
        fn = getattr(reset_helper, name, None)
        if callable(fn):
            try:
                fn(context)
                return True
            except Exception as ex:
                print(f"[auto_calibrate] reset_helper.{name} failed: {ex}")
    # Fallback: kleiner Minimal-Reset (Playhead zurück)
    try:
        if hasattr(context, "scene"):
            context.scene.frame_current = context.scene.frame_start
        return True
    except Exception:
        return False


class KAISERLICHTRACKER_OT_auto_calibrate(Operator):
    """
    Snapshot -> Detect/Adapt -> (optional Track) -> Auswertung (Gesamtlänge NEUER Tracks)
    -> Cleanup (NEUE löschen) -> Reset (Szene zurücksetzen).
    """
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto Calibrate Tracking (Total Length + Cleanup + Reset)"
    bl_options = {"REGISTER", "UNDO"}

    run_tracking_step: bpy.props.BoolProperty(  # type: ignore
        name="Tracking ausführen",
        default=True,
        description="Tracking-Operator nach Detect/Adapt ausführen"
    )
    start_frame: bpy.props.IntProperty(  # type: ignore
        name="Start Frame",
        default=1,
        min=0,
        description="Ab diesem Frame wird die Länge gezählt"
    )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({"ERROR"}, "Kein aktiver MovieClip im Clip-Editor.")
            return {"CANCELLED"}

        # 1) Snapshot: vorhandene Track-Namen als Baseline
        pre_snapshot = snapshot_active_markers(context)
        baseline_names = {m.get("track") for m in pre_snapshot if m.get("track")}
        self.report({"INFO"}, f"Baseline: {len(baseline_names)} Tracks.")

        # 2) Detect/Adapt
        if not _safe_run_detect_adapt(context):
            self.report({"WARNING"}, "Detect/Adapt konnte nicht automatisch gestartet werden.")

        # 3) Tracking (optional)
        if self.run_tracking_step and not _safe_run_tracking(context):
            self.report({"INFO"}, "Tracking-Schritt übersprungen oder kein Einstiegspunkt gefunden.")

        # 4) Auswertung (nur neue Tracks)
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({"ERROR"}, "Clip hat kein Tracking-Objekt.")
            return {"CANCELLED"}

        all_names = [t.name for t in tracking.tracks]
        new_names = [n for n in all_names if n not in baseline_names]
        total_length = _total_length_for_tracks(clip, new_names, start_frame=self.start_frame)
        clip["new_tracks_total_length"] = int(total_length)  # optional für UI/Debug
        self.report({"INFO"}, f"Gesamtlänge neuer Tracks: {int(total_length)} Frames")

        # 5) Cleanup (nur neue Tracks löschen)
        removed = _safe_delete_tracks(context, set(new_names))
        self.report({"INFO"}, f"Cleanup: {removed} neue Tracks gelöscht. Baseline bleibt erhalten.")

        # 6) Reset (Szene wiederherstellen)
        if _safe_reset(context):
            self.report({"INFO"}, "Reset: Szene in Ausgangszustand versetzt.")
        else:
            self.report({"WARNING"}, "Reset: Kein passender Reset-Aufruf gefunden, minimaler Fallback ausgeführt.")

        return {"FINISHED"}
