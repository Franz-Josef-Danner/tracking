# Operator/auto_calibrate_operator.py
from __future__ import annotations
import bpy
from bpy.types import Operator
from ..Helper.snapshot import snapshot_active_markers
from ..Operator import detect_adapt_operator, track_operator  # vorhanden laut Projektstruktur


def _find_track_by_name(tracking: bpy.types.MovieTracking, name: str):
    """Hole Track wahlweise aus active object oder root-set."""
    if getattr(tracking.objects, "active", None):
        tr = tracking.objects.active.tracks.get(name)
        if tr:
            return tr
    return tracking.tracks.get(name)


def _total_length_for_tracks(clip: bpy.types.MovieClip, track_names, start_frame: int = 1) -> int:
    """Summiert Segmentlängen über alle angegebenen Tracks (Lücke > 1 trennt Segmente)."""
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
    """Versucht gängige Einstiegspunkte oder bpy.ops für den Tracking-Durchlauf."""
    # häufige Funktionsnamen im track_operator
    for name in ("track_cycle", "run", "main", "execute"):
        fn = getattr(track_operator, name, None)
        if callable(fn):
            try:
                # track_cycle hat oft Parameter; mit Defaults aufrufen
                fn(context)
                return True
            except TypeError:
                # Versuch mit typischen Signaturen
                try:
                    fn(context, max_frames=0)
                    return True
                except Exception as ex:
                    print(f"[auto_calibrate] track_operator.{name}(context, max_frames=0) failed: {ex}")
            except Exception as ex:
                print(f"[auto_calibrate] track_operator.{name} failed: {ex}")

    # Fallback: Operator
    try:
        result = bpy.ops.kaiserlich_tracker.track()
        return result == {"FINISHED"}
    except Exception as ex:
        print(f"[auto_calibrate] bpy.ops track failed: {ex}")
        return False


class KAISERLICHTRACKER_OT_auto_calibrate(Operator):
    """Snapshot -> Detect/Adapt -> Track -> Gesamtlänge neuer Tracks."""
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

        # 1) Snapshot vor Detect/Track
        pre_snapshot = snapshot_active_markers(context)
        baseline_names = {m.get("track") for m in pre_snapshot if m.get("track")}
        self.report({"INFO"}, f"Baseline: {len(baseline_names)} Tracks.")

        # 2) Detect/Adapt (legt neue Marker/Tracks an)
        if not _safe_run_detect_adapt(context):
            self.report({"WARNING"}, "Detect/Adapt konnte nicht automatisch gestartet werden.")

        # 3) Tracking-Operator ausführen (Tracks wirklich verfolgen/verlängern)
        if not _safe_run_tracking(context):
            self.report({"INFO"}, "Tracking-Schritt wurde übersprungen oder kein Einstiegspunkt gefunden.")

        # 4) Auswertung: nur neue Tracks seit Baseline summieren
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({"ERROR"}, "Clip hat kein Tracking-Objekt.")
            return {"CANCELLED"}

        all_names = [t.name for t in tracking.tracks]
        new_names = [n for n in all_names if n not in baseline_names]

        total_length = _total_length_for_tracks(clip, new_names, start_frame=self.start_frame)
        clip["new_tracks_total_length"] = int(total_length)  # optional für UI/Debug

        self.report({"INFO"}, f"Gesamtlänge neuer Tracks: {int(total_length)} Frames")
        return {"FINISHED"}
