# Operator/auto_calibrate_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator

# Snapshot nutzt euer bestehendes Helper-Modul
from ..Helper.snapshot import snapshot_active_markers
# für das Löschen nutzen wir euer delete-Helper (falls vorhanden) + Fallback
from ..Helper import delete as delete_helper
# optional: direkte Modulzugriffe (falls ihr lieber Funktionsaufrufe statt bpy.ops nutzt)
from ..Operator import detect_adapt_operator, track_operator  # nur verwendet, wenn Funktionen existieren


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
    """Versucht gängige Einstiegspunkte oder bpy.ops für Detect/Adapt."""
    for name in ("run_detect_and_adapt", "run", "main", "execute"):
        fn = getattr(detect_adapt_operator, name, None)
        if callable(fn):
            try:
                fn(context)
                return True
            except Exception as ex:
                print(f"[auto_calibrate] detect_adapt_operator.{name} failed: {ex}")
    try:
        result = bpy.ops.kaiserlich_tracker.detect_adapt()
        return result == {"FINISHED"}
    except Exception as ex:
        print(f"[auto_calibrate] bpy.ops detect_adapt failed: {ex}")
        return False


def _safe_run_tracking(context) -> bool:
    """Tracking-Operator ausführen (falls separat nötig)."""
    for name in ("track_cycle", "run", "main", "execute"):
        fn = getattr(track_operator, name, None)
        if callable(fn):
            try:
                fn(context)
                return True
            except TypeError:
                try:
                    fn(context, max_frames=0)  # häufige Signatur
                    return True
                except Exception as ex:
                    print(f"[auto_calibrate] track_operator.{name}(context, max_frames=0) failed: {ex}")
            except Exception as ex:
                print(f"[auto_calibrate] track_operator.{name} failed: {ex}")
    try:
        result = bpy.ops.kaiserlich_tracker.track()
        return result == {"FINISHED"}
    except Exception as ex:
        print(f"[auto_calibrate] bpy.ops track failed: {ex}")
        return False


def _safe_delete_tracks(context, names: set[str]) -> int:
    """
    Löscht alle Tracks mit Namen in 'names'.
    1) versucht delete-Helper (falls API vorhanden),
    2) Fallback: entfernt Tracks direkt aus bpy.
    Rückgabe: Anzahl gelöschter Tracks.
    """
    # 1) Versuch: Helper-APIs
    for candidate in ("delete_tracks_by_names", "delete_tracks", "remove_tracks_by_name"):
        func = getattr(delete_helper, candidate, None)
        if callable(func):
            try:
                return int(func(context, list(names)))
            except Exception as ex:
                print(f"[auto_calibrate] delete_helper.{candidate} failed: {ex}")

    # 2) Fallback: direkte Entfernung
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return 0
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return 0

    to_remove = []
    # sowohl active object als auch root berücksichtigen
    collections = []
    if getattr(tracking.objects, "active", None):
        collections.append(tracking.objects.active.tracks)
    collections.append(tracking.tracks)

    for tracks in collections:
        for tr in list(tracks):
            if tr.name in names:
                to_remove.append((tracks, tr))

    removed = 0
    for tracks, tr in to_remove:
        try:
            tracks.remove(tr)
            removed += 1
        except Exception as ex:
            print(f"[auto_calibrate] removing track '{tr.name}' failed: {ex}")

    return removed


class KAISERLICHTRACKER_OT_auto_calibrate(Operator):
    """
    Snapshot -> Detect/Adapt -> (optional Track) -> Auswertung (Gesamtlänge NEUER Tracks)
    -> Cleanup (NEUE Tracks löschen).
    """
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto Calibrate Tracking (Total Length + Cleanup)"
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
        description="Ab diesem Frame wird gezählt"
    )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({"ERROR"}, "Kein aktiver MovieClip im Clip-Editor.")
            return {"CANCELLED"}

        # --- 1) Snapshot: vorhandene Track-Namen als Baseline ---
        pre_snapshot = snapshot_active_markers(context)
        baseline_names = {m.get("track") for m in pre_snapshot if m.get("track")}
        self.report({"INFO"}, f"Baseline: {len(baseline_names)} Tracks.")

        # --- 2) Detect/Adapt: neue Marker/Tracks werden angelegt ---
        if not _safe_run_detect_adapt(context):
            self.report({"WARNING"}, "Detect/Adapt konnte nicht automatisch gestartet werden.")

        # --- 3) Tracking-Schritt (falls eure Pipeline das trennt) ---
        if self.run_tracking_step:
            if not _safe_run_tracking(context):
                self.report({"INFO"}, "Tracking-Schritt übersprungen oder kein Einstiegspunkt gefunden.")

        # --- 4) Auswertung: nur neue Tracks seit Baseline summieren ---
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({"ERROR"}, "Clip hat kein Tracking-Objekt.")
            return {"CANCELLED"}

        all_names = [t.name for t in tracking.tracks]
        new_names = [n for n in all_names if n not in baseline_names]
        total_length = _total_length_for_tracks(clip, new_names, start_frame=self.start_frame)
        clip["new_tracks_total_length"] = int(total_length)  # optional für UI/Debug
        self.report({"INFO"}, f"Gesamtlänge neuer Tracks: {int(total_length)} Frames")

        # --- 5) Cleanup: alle NEUEN Tracks löschen ---
        removed = _safe_delete_tracks(context, set(new_names))
        self.report({"INFO"}, f"Cleanup: {removed} neue Tracks gelöscht. Baseline-Tracks bleiben erhalten.")

        return {"FINISHED"}
