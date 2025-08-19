# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper: tracking_helper – reine Funktionsvariante

Dieses Modul stellt **keinen Operator** bereit, sondern ausschließlich
Funktionen, die von Operatoren (z. B. einem Orchestrator) aufgerufen
werden können. Kern ist `track_to_scene_end_fn(...)`, die die Tracking-
Pipeline synchron bis zum Szenenende ausführt und am Ende optional ein
WindowManager-Token setzt, damit ein wartender Operator sauber finishen
kann.

Konzept (aus Vorgabe übernommen, leicht verdichtet):
- Bootstrap (Lock zurücksetzen, Marker-Korridor bestimmen, ggf. Defaults anwenden)
- Loop: Find Low → Jump → Detect (timeboxed) → Track FWD/BWD → Clean Short
- Ende: Solve → optional Refine → Projection-Cleanup → Finalize

Wichtige Scene-Schlüssel (werden gelesen/gesetzt):
- scene["__detect_lock"]: bool – exklusiver Abschnitt für Detektion
- scene["marker_basis"], ["marker_adapt"], ["marker_min"], ["marker_max"],
  ["frames_track"], ["resolve_error"], ["error_track"]
- scene["goto_frame"]: int – Zielbild für Detektion

Hinweis: Diese Implementierung ist robust gegen fehlende Scene-Keys
(legt Defaults an) und kapselt Blender-Operatoraufrufe mit Try/Except,
um den FSM-Fluss nicht unnötig zu unterbrechen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import bpy

__all__ = (
    "track_to_scene_end_fn",
    "_redraw_clip_editors",
    # Optionale Helfer für Unit-Tests / Re-Use:
    "marker_helper_main",
    "main_to_adapt",
    "apply_tracker_settings",
    "run_find_low_marker_frame",
    "run_jump_to_frame",
    "run_detect_once",
    "clean_short_tracks",
    "run_solve_watch_clean",
    "builtin_projection_cleanup",
)


# -----------------------------------------------------------------------------
# Utility / Datamodel
# -----------------------------------------------------------------------------

@dataclass
class DetectResult:
    status: str  # "READY" | "RUNNING" | "FAILED"
    frame: int
    threshold: float
    new_tracks: int


def _wm(context: bpy.types.Context):
    return context.window_manager


def _scene(context: bpy.types.Context):
    return context.scene


def _clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    sp: Optional[bpy.types.SpaceClipEditor]
    sp = getattr(context, "space_data", None)
    if sp and sp.type == 'CLIP_EDITOR' and sp.clip:
        return sp.clip
    # Fallback: aktiven Clip über Tracking-Settings suchen
    try:
        return context.scene.clip
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Öffentliche Kernfunktion
# -----------------------------------------------------------------------------

def track_to_scene_end_fn(
    context: bpy.types.Context,
    *,
    coord_token: Optional[str] = None,
    use_invoke: bool = False,
    do_backward: bool = True,
    auto_clean_short: bool = True,
    use_apply_settings: bool = True,
    detect_timebox: int = 8,
    clean_action: str = 'DELETE_TRACK',  # 'DELETE_TRACK' | 'DELETE_SEGMENTS'
    cleanup_mute_only: bool = False,
    refine_limit_frames: int = 0,
) -> None:
    """Führt die gesamte Tracking-Pipeline synchron aus.

    Parameter sind so gewählt, dass Operatoren die Funktion flexibel
    nutzen können (INVOCATION-Modus, bidirektionales Tracking, usw.).
    Am Ende setzt die Funktion optional ein Feedback-Token in den
    WindowManager und triggert einen Viewer-Redraw.
    """
    scn = _scene(context)
    wm = _wm(context)

    # --- Bootstrap
    try:
        scn["__detect_lock"] = False
    except Exception:
        pass

    marker_helper_main(context)
    main_to_adapt(context, use_override=True)

    if use_apply_settings:
        apply_tracker_settings(context)

    start_frame = int(scn.frame_start)
    end_frame = int(scn.frame_end)
    tracked_until = start_frame

    # --- Hauptloop
    while True:
        find = run_find_low_marker_frame(context)
        if find.get("status") == "NONE":
            print("[FSM] FIND_LOW → NONE → SOLVE")
            break

        # Found/Failed werden gleich behandelt: wir versuchen best effort.
        goto = int(find.get("frame", scn.frame_current))
        scn["goto_frame"] = goto

        run_jump_to_frame(context, frame=goto)

        # Timeboxed Detection
        attempts = 0
        while True:
            dres = run_detect_once(context, start_frame=goto, use_invoke=use_invoke)
            status = dres.status
            if status == "READY":
                print(f"[FSM] DETECT → READY (thr={dres.threshold:.3f}, new={dres.new_tracks})")
                break
            if status == "FAILED":
                print("[FSM] DETECT → FAILED → TRACK_FWD")
                break
            attempts += 1
            if attempts >= max(1, int(detect_timebox)):
                print("[FSM] DETECT → TIMEBOX reached → TRACK_FWD")
                break

        # Forward tracking
        try:
            bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False)
        except Exception as ex:
            print(f"[TrackFwd] Fehler: {ex}")
        else:
            tracked_until = end_frame  # Heuristik: Blender trackt bis Ende

        # Backward tracking (optional)
        if do_backward:
            try:
                bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=True)
            except Exception as ex:
                print(f"[TrackBwd] Fehler: {ex}")

        # Cleanup short tracks
        if auto_clean_short:
            frames = int(scn.get("frames_track", 25))
            try:
                clean_short_tracks(context, action=clean_action, frames=frames)
            except Exception as ex:
                print(f"[CleanShort] Fehler: {ex}")

        # Loop zurück zu FIND_LOW
        print("[FSM] → FIND_LOW (nächster Zyklus)")

    # --- SOLVE & Cleanup
    try:
        bpy.ops.clip.solve_camera('EXEC_DEFAULT')
    except Exception as ex:
        print(f"[Solve] Fehler: {ex}")

    if refine_limit_frames > 0:
        try:
            run_refine_on_high_error(context, limit_frames=refine_limit_frames)
            bpy.ops.clip.solve_camera('EXEC_DEFAULT')
        except Exception as ex:
            print(f"[Refine] Fehler: {ex}")

    # Projection Cleanup anhand resolve_error (Fallback auf error_track)
    thr = float(scn.get("resolve_error", scn.get("error_track", 2.0)))
    try:
        builtin_projection_cleanup(
            context,
            threshold=thr,
            action=('MUTE' if cleanup_mute_only else 'DELETE_TRACK'),
        )
    except Exception as ex:
        print(f"[ProjCleanup] Fehler: {ex}")

    # Final: Playhead reset, Redraw & Token setzen
    try:
        scn.frame_current = start_frame
    except Exception:
        pass
    try:
        _redraw_clip_editors(context)
    except Exception:
        pass

    if coord_token:
        try:
            wm["bw_tracking_done_token"] = coord_token
            wm["bw_tracking_last_info"] = {
                "start_frame": start_frame,
                "tracked_until": tracked_until,
            }
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Bootstrap-Helpers
# -----------------------------------------------------------------------------

def marker_helper_main(context: bpy.types.Context) -> Tuple[bool, float, Dict[str, float]]:
    """Bestimmt Marker-Korridor und legt Scene-Keys an.

    Returns (ok, adapt_val, op_result)
    """
    scn = _scene(context)
    marker_basis = int(getattr(scn, "marker_frame", 25))
    frames_track = int(getattr(scn, "frames_track", 25))
    error_track = float(getattr(scn, "error_track", 2.0))

    factor = 4.0
    marker_adapt = max(1, int(marker_basis * factor * 0.9))
    marker_min = max(1, int(marker_adapt * 0.9))
    marker_max = max(marker_min, int(marker_adapt * 1.1))

    scn["marker_basis"] = marker_basis
    scn["marker_adapt"] = marker_adapt
    scn["marker_min"] = marker_min
    scn["marker_max"] = marker_max
    scn["frames_track"] = frames_track
    scn["error_track"] = error_track

    print(
        f"[MarkerHelper] basis={marker_basis}, adapt={marker_adapt}, "
        f"min={marker_min}, max={marker_max}, frames_track={frames_track}, error_track={error_track}"
    )
    return True, float(marker_adapt), {
        "marker_basis": marker_basis,
        "marker_adapt": marker_adapt,
        "marker_min": marker_min,
        "marker_max": marker_max,
        "frames_track": frames_track,
        "error_track": error_track,
    }


def main_to_adapt(context: bpy.types.Context, *, use_override: bool = True) -> None:
    """Konsolidiert ggf. Werte – hier minimal: Sicherstellen, dass adapt vorhanden ist."""
    scn = _scene(context)
    if use_override or ("marker_adapt" not in scn.keys()):
        adapt = int(scn.get("marker_adapt", 20))
        scn["marker_adapt"] = max(1, adapt)


def apply_tracker_settings(context: bpy.types.Context) -> None:
    """Setzt sinnvolle Defaults für Tracker/Detection.

    Abhängig von der Clip-Größe könnte man hier dynamisch anpassen;
    wir setzen robuste Standardwerte.
    """
    try:
        # Beispielhafte Defaults: Pattern/ Search Size usw.
        ts = bpy.context.scene.tracking.settings
        ts.default_pattern_size = 15
        ts.default_search_size = 75
        ts.default_motion_model = 'Affine'
        ts.correlation_min = 0.75
        # Startthreshold für Detect
        _scn = _scene(context)
        _scn['last_detection_threshold'] = 0.5
        print("[ApplySettings] Defaults gesetzt")
    except Exception as ex:
        print(f"[ApplySettings] Fehler: {ex}")


# -----------------------------------------------------------------------------
# FSM-Helpers
# -----------------------------------------------------------------------------

def run_find_low_marker_frame(context: bpy.types.Context) -> Dict[str, int]:
    """Sucht den ersten Frame unterhalb der Markerschwelle.

    Heuristik: Wir zählen aktive Tracks pro Frame grob über die Länge
    der Tracking-Daten. Für eine performante, präzise Auswertung könnte
    man MovieClip.tracking.reconstruction/Tracks iterieren.
    """
    scn = _scene(context)
    clip = _clip(context)
    if not clip:
        return {"status": "FAILED", "frame": int(scn.frame_current)}

    start = int(scn.frame_start)
    end = int(scn.frame_end)
    adapt = int(scn.get("marker_adapt", 20))

    # Sehr vereinfachte Zählung pro Frame: wir nehmen den aktuellen Frame,
    # und wenn Markerspurzahl unter adapt liegt → FOUND.
    # Für echtes Projekt: Histogramm über alle Frames erstellen.
    cur = int(scn.frame_current)
    visible_tracks = sum(1 for t in clip.tracking.tracks if t.select)
    if visible_tracks < adapt:
        return {"status": "FOUND", "frame": cur}

    # Als Fallback: starte am Anfang – typisch ist Frame 1 ohne Marker.
    return {"status": "FOUND", "frame": start}


def run_jump_to_frame(context: bpy.types.Context, *, frame: int) -> None:
    scn = _scene(context)
    try:
        scn.frame_current = int(frame)
    except Exception as ex:
        print(f"[Jump] Fehler: {ex}")


def run_detect_once(
    context: bpy.types.Context,
    *,
    start_frame: int,
    use_invoke: bool = False,
) -> DetectResult:
    scn = _scene(context)

    # Critical section
    scn["__detect_lock"] = True
    try:
        # adaptiven Threshold nutzen
        thr = float(scn.get('last_detection_threshold', 0.5))
        # Detect ausführen
        try:
            if use_invoke:
                bpy.ops.clip.detect_features('INVOKE_DEFAULT', placement='FRAME', threshold=thr)
            else:
                bpy.ops.clip.detect_features('EXEC_DEFAULT', placement='FRAME', threshold=thr)
        except Exception as ex:
            print(f"[Detect] Ausnahme: {ex}")
            return DetectResult(status="FAILED", frame=start_frame, threshold=thr, new_tracks=0)

        # Nach Detect heuristisch prüfen, wie viele neue Tracks selektiert sind
        clip = _clip(context)
        new_tracks = 0
        if clip:
            new_tracks = sum(1 for t in clip.tracking.tracks if t.select)

        adapt = int(scn.get("marker_adapt", 20))
        if new_tracks >= adapt:
            scn['last_detection_threshold'] = thr  # behalten
            return DetectResult(status="READY", frame=start_frame, threshold=thr, new_tracks=new_tracks)
        else:
            # Threshold etwas absenken und erneut probieren
            thr = max(0.05, thr * 0.8)
            scn['last_detection_threshold'] = thr
            return DetectResult(status="RUNNING", frame=start_frame, threshold=thr, new_tracks=new_tracks)
    finally:
        scn["__detect_lock"] = False


def clean_short_tracks(
    context: bpy.types.Context,
    *,
    frames: int,
    action: str = 'DELETE_TRACK',
) -> None:
    try:
        bpy.ops.clip.clean_tracks('EXEC_DEFAULT', frames=int(frames), error=0.0, action=action)
        print(f"[CleanShort] frames<{frames} → {action}")
    except Exception as ex:
        print(f"[CleanShort] Fehler: {ex}")


# -----------------------------------------------------------------------------
# Solve & Cleanup
# -----------------------------------------------------------------------------

def run_refine_on_high_error(context: bpy.types.Context, *, limit_frames: int = 0) -> None:
    """Platzhalter: gezielte Nachbesserung auf Top-Fehlerframes.

    In einem realen Setup wählt man die Frames mit größtem Reproj-Error
    und führt dort lokale Re-Detection/Re-Tracking aus.
    """
    if limit_frames <= 0:
        return
    print(f"[Refine] (mock) refine_high_error on top {limit_frames} frames…")


def builtin_projection_cleanup(
    context: bpy.types.Context,
    *,
    threshold: float,
    action: str = 'DELETE_TRACK',  # oder 'MUTE'
) -> None:
    try:
        bpy.ops.clip.clean_tracks('EXEC_DEFAULT', frames=0, error=float(threshold), action=action)
        print(f"[ProjCleanup] error>{threshold:.3f} → {action}")
    except Exception as ex:
        print(f"[ProjCleanup] Fehler: {ex}")


def run_solve_watch_clean(context: bpy.types.Context) -> None:
    try:
        bpy.ops.clip.solve_camera('EXEC_DEFAULT')
    except Exception as ex:
        print(f"[Solve] Fehler: {ex}")


# -----------------------------------------------------------------------------
# Viewer-Redraw
# -----------------------------------------------------------------------------

def _redraw_clip_editors(context: bpy.types.Context) -> None:
    """Forciert Redraw im CLIP_EDITOR über alle Fenster/Regionen."""
    wm = _wm(context)
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            for region in area.regions:
                if region.type == 'WINDOW':
                    region.tag_redraw()
