# Operator/auto_calibrate_operator.py  (Ergänzungen)
from __future__ import annotations
import bpy
from bpy.types import Operator

# Vorhandene Helfer/Module aus deinem Projekt:
from ..Helper.snapshot import snapshot_active_markers
from ..Helper import delete as delete_helper
from ..Helper import reset_helper
from ..Operator import detect_adapt_operator

# ------------------------------------------------------------
# Hilfsfunktionen (lokal)
# ------------------------------------------------------------

def _active_clip(context) -> bpy.types.MovieClip | None:
    return getattr(context.space_data, "clip", None)


def _tracking(clip: bpy.types.MovieClip) -> bpy.types.MovieTracking | None:
    return getattr(clip, "tracking", None)


def _find_track_by_name(tracking: bpy.types.MovieTracking, name: str):
    """Hole Track wahlweise aus active object oder root-set."""
    if getattr(tracking.objects, "active", None):
        tr = tracking.objects.active.tracks.get(name)
        if tr:
            return tr
    return tracking.tracks.get(name)


def _total_length_for_tracks(clip: bpy.types.MovieClip, track_names, start_frame: int = 1) -> int:
    """
    Summiert Segmentlängen über alle angegebenen Tracks.
    Ein Segment ist eine Folge aufeinanderfolgender Frames (Lücke > 1 trennt Segmente).
    """
    tracking = _tracking(clip)
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
        return bpy.ops.kaiserlich_tracker.detect_adapt() == {"FINISHED"}
    except Exception as ex:
        print(f"[auto_calibrate] bpy.ops detect_adapt failed: {ex}")
        return False


def _safe_delete_tracks(context, names: set[str]) -> int:
    """
    Löscht alle Tracks in 'names'.
    1) versucht Helper-APIs,
    2) Fallback: direkte Entfernung aus bpy.
    """
    for candidate in ("delete_tracks_by_names", "delete_tracks", "remove_tracks_by_name"):
        func = getattr(delete_helper, candidate, None)
        if callable(func):
            try:
                return int(func(context, list(names)))
            except Exception as ex:
                print(f"[auto_calibrate] delete_helper.{candidate} failed: {ex}")

    clip = _active_clip(context)
    if clip is None:
        return 0
    tracking = _tracking(clip)
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
    """Reset der Szene über reset_helper; Fallback: Playhead zurück."""
    for name in ("reset_scene", "reset_all", "restore_initial_state", "reset"):
        fn = getattr(reset_helper, name, None)
        if callable(fn):
            try:
                fn(context)
                return True
            except Exception as ex:
                print(f"[auto_calibrate] reset_helper.{name} failed: {ex}")
    try:
        if hasattr(context, "scene"):
            context.scene.frame_current = context.scene.frame_start
        return True
    except Exception:
        return False


def _selected_tracks(context) -> list[bpy.types.MovieTrackingTrack]:
    """Selektierte Tracks aus aktivem Objekt oder Root-Set ermitteln."""
    clip = _active_clip(context)
    if not clip:
        return []
    tracking = _tracking(clip)
    if not tracking:
        return []
    candidates = []
    if getattr(tracking.objects, "active", None):
        candidates.extend(list(tracking.objects.active.tracks))
    candidates.extend(list(tracking.tracks))
    return [t for t in candidates if getattr(t, "select", False)]


# ------------------------------------------------------------
# Öffentliche API: run_tracking_cycle(context)
# -> Snapshot -> Detect/Adapt -> TrackCycle -> Länge -> Cleanup -> Reset
# ------------------------------------------------------------

def run_tracking_cycle(context, start_frame: int = 1,
                       do_cleanup: bool = True,
                       do_reset: bool = True) -> int:
    """
    Führt einen kompletten Trackingdurchlauf aus und liefert die
    GESAMTLÄNGE der *neu hinzugekommenen* Tracks zurück.

    Ablauf:
      1) Snapshot Baseline (bestehende Tracks)
      2) Detect/Adapt (legt neue Marker/Tracks an)
      3) Frameweises Tracking der selektierten Marker (Operator unten)
      4) Auswertung: Gesamtlänge NEUER Tracks ab start_frame
      5) Cleanup: löscht NEUE Tracks
      6) Reset: stellt die Szene zurück
    """
    clip = _active_clip(context)
    if clip is None:
        return 0

    # 1) Snapshot
    pre_snapshot = snapshot_active_markers(context)
    baseline_names = {m.get("track") for m in pre_snapshot if m.get("track")}

    # 2) Detect/Adapt
    _safe_run_detect_adapt(context)

    # 3) TrackCycle
    try:
        bpy.ops.kaiserlich_tracker.track_cycle()
    except Exception as ex:
        print(f"[auto_calibrate] track_cycle op failed: {ex}")

    # 4) Auswertung
    tracking = _tracking(clip)
    if not tracking:
        return 0
    all_names = [t.name for t in tracking.tracks]
    new_names = [n for n in all_names if n not in baseline_names]
    total_length = _total_length_for_tracks(clip, new_names, start_frame=start_frame)

    # 5) Cleanup
    if do_cleanup and new_names:
        _safe_delete_tracks(context, set(new_names))

    # 6) Reset
    if do_reset:
        _safe_reset(context)

    return int(total_length)


# ------------------------------------------------------------
# 1️⃣ Kurztest (vereinfacht mit Reset & Snapshot)
#    -> nutzt run_tracking_cycle(context) als Blackbox
# ------------------------------------------------------------

def _short_test(context):
    """
    Vereinfacht: für jede Schwellenwert-Kombi:
      - beide Props auf min_threshold setzen
      - Tracking-Cycle laufen lassen (Snapshot/Detect/Track/Auswertung/Cleanup/Reset)
      - Thresholds wieder zurücksetzen
    Erwartet:
      - thresh_liste = [{"props": (pA, pB)}, ...]
      - set_scene_value(prop, value)
      - reset_all_thresholds(context, [pA, pB])
      - min_threshold (z. B. 0.0 oder 1)
    Diese Symbole stammen aus deinem bestehenden Projekt/Umfeld.
    """
    # Annahme: diese Symbole existieren bereits im Modul-Kontext
    try:
        thresh_iter = iter(thresh_liste)  # noqa: F821  # kommt aus eurem bestehenden Code
    except NameError:
        print("[auto_calibrate] _short_test: 'thresh_liste' nicht definiert.")
        return

    results = []
    for thresh in thresh_iter:
        props = thresh.get("props", ())
        if len(props) == 2:
            pA, pB = props
            try:
                set_scene_value(pA, min_threshold)  # noqa: F821
                set_scene_value(pB, min_threshold)  # noqa: F821
            except Exception as ex:
                print(f"[auto_calibrate] _short_test: set_scene_value failed: {ex}")

            length = run_tracking_cycle(context)  # liefert eine einzige Zahl
            results.append({"props": (pA, pB), "total_length": length})

            try:
                reset_all_thresholds(context, [pA, pB])  # noqa: F821
            except Exception as ex:
                print(f"[auto_calibrate] _short_test: reset_all_thresholds failed: {ex}")

    # Optional: Ergebnis verfügbar machen (z. B. für UI/Logging)
    context.scene["short_test_results"] = results


# ------------------------------------------------------------
# Operator: Frameweises Tracken (stabil für Blender 4.4+)
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_track_cycle(Operator):
    """Trackt selektierte Marker frameweise, stabiler Ablauf für Blender 4.4+."""
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Zyklus (Frame für Frame)"
    bl_description = (
        "Trackt die aktuell selektierten Tracks frameweise vorwärts, "
        "bis das Szenen-Ende erreicht wurde."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    step_limit: bpy.props.IntProperty(  # type: ignore
        name="Max Steps (0=alle)",
        default=0,
        min=0,
        description="Maximale Anzahl Einzelschritte (0 = bis Szenenende)."
    )

    def execute(self, context):
        clip = _active_clip(context)
        if not clip:
            self.report({"ERROR"}, "Kein aktiver MovieClip im Clip-Editor.")
            return {"CANCELLED"}

        scene = context.scene
        end_frame = scene.frame_end
        steps_left = int(self.step_limit) if self.step_limit > 0 else None

        # Sicherstellen, dass es selektierte Tracks gibt
        sel = _selected_tracks(context)
        if not sel:
            self.report({"INFO"}, "Keine selektierten Tracks – nichts zu tracken.")
            return {"CANCELLED"}

        # Frameweise tracken: pro Schritt nur ein Forward-Step
        # bpy.ops.clip.track_markers(sequence=False) => Einzelbild
        while scene.frame_current < end_frame:
            try:
                bpy.ops.clip.track_markers(backwards=False, sequence=False)
            except Exception as ex:
                print(f"[track_cycle] track_markers failed: {ex}")
                break

            scene.frame_current += 1

            if steps_left is not None:
                steps_left -= 1
                if steps_left <= 0:
                    break

        return {"FINISHED"}
