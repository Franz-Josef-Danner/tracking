# Helper/prune_tracks_density.py

import bpy
from typing import List, Tuple, Optional

from .find_max_marker_frame import get_active_marker_counts_sorted  # (context) -> List[(frame, count)]
from .error_value import error_value  # berechnet StdAbw X+Y für selektierte Marker im aktiven Clip

# -- Kontext-Helfer -----------------------------------------------------------

def _get_clip_editor_handles(context: bpy.types.Context):
    """Liefert (area, region_window, space_clip) des aktiven Clip-Editors, sonst (None, None, None)."""
    screen = getattr(context, "screen", None)
    if not screen:
        return None, None, None
    for area in screen.areas:
        if area.type == 'CLIP_EDITOR':
            # Hole WINDOW-Region
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            space = area.spaces.active
            if region_window and getattr(space, "clip", None):
                return area, region_window, space
    # Fallback: aktueller space_data (sofern Clip vorhanden)
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        # region/window fehlt → Operator-Aufrufe könnten scheitern; nur für reine Lesezugriffe geeignet
        return None, None, space
    return None, None, None

def _get_clip_from_context(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    _, _, space = _get_clip_editor_handles(context)
    return getattr(space, "clip", None) if space else None

# -- Frame/Marker Utilities ---------------------------------------------------

def _frame_active_markers(clip: bpy.types.MovieClip, frame: int):
    """
    Liefert Liste (Track, Marker) aller *aktiven* Marker auf genau diesem Frame.
    Aktiv = marker.mute == False.
    """
    out = []
    for tr in clip.tracking.tracks:
        mk = tr.markers.find_frame(frame)
        if not mk:
            continue
        if getattr(mk, "mute", False):
            continue
        out.append((tr, mk))
    return out

# -- Error je Track (isoliert, mit sicherem Override) -------------------------

def _compute_track_error_isolated(context: bpy.types.Context,
                                  scene: bpy.types.Scene,
                                  track: bpy.types.MovieTrackingTrack) -> Optional[float]:
    """
    Selektiert transient GENAU diesen Track, ruft error_value(scene) im gültigen Clip-Editor-Kontext auf
    und stellt die Selektion wieder her.
    """
    area, region, space = _get_clip_editor_handles(context)
    clip = getattr(space, "clip", None) if space else None
    if not clip:
        return None

    # Selektion sichern
    prev_selection = {t.name: bool(t.select) for t in clip.tracking.tracks}
    try:
        # Nur Zieltrack selektieren
        for t in clip.tracking.tracks:
            t.select = (t == track)

        # error_value liest bpy.context.space_data.clip → daher mit Override ausführen
        with context.temp_override(area=area, region=region, space_data=space):
            val = error_value(scene)
        return float(val) if val is not None else None
    finally:
        # Selektion restaurieren
        for t in clip.tracking.tracks:
            t.select = prev_selection.get(t.name, False)

# -- Track löschen (Operator, kontextkonform) --------------------------------

def _delete_track(context: bpy.types.Context,
                  track: bpy.types.MovieTrackingTrack) -> bool:
    """
    Löscht den gegebenen Track per bpy.ops.clip.delete_track(confirm=False).
    Voraussetzung: gültiger Clip-Editor-Kontext.
    Rückgabe True bei Erfolg.
    """
    area, region, space = _get_clip_editor_handles(context)
    clip = getattr(space, "clip", None) if space else None
    if not clip or not area or not region:
        return False

    # Selektion: nur den Zieltrack selektieren
    prev_selection = {t.name: bool(t.select) for t in clip.tracking.tracks}
    try:
        for t in clip.tracking.tracks:
            t.select = (t == track)

        with context.temp_override(area=area, region=region, space_data=space):
            res = bpy.ops.clip.delete_track(confirm=False)  # Delete selected tracks
            ok = (res == {'FINISHED'})
    finally:
        # Restorative Selektion – minimiert Seiteneffekte
        for t in clip.tracking.tracks:
            t.select = prev_selection.get(t.name, False)

    return ok

# -- Hauptlogik ---------------------------------------------------------------

def prune_tracks_density(
    context: bpy.types.Context,
    *,
    threshold_key: str = "marker_frame",    # Ziel: auf jedem Frame auf <= scene[threshold_key] * 2 Marker eindampfen
    prefer_earliest_on_tie: bool = True,    # (Reserviert, falls du später Tie-Break ändern willst)
    dry_run: bool = False,                  # nur analysieren, nicht löschen
) -> dict:
    """
    Pipeline:
      1) Hole sortierte Liste (frame, count) aus get_active_marker_counts_sorted(context), absteigend.
      2) Definiere Threshold = scene[threshold_key] * 2 (Default: 20*2, falls Key fehlt).
      3) Für jeden Frame mit count > Threshold:
           - Ermittele aktive Marker/Tracks am Frame
           - Solange aktuelle Markermenge > Threshold:
               a) Bestimme pro Track ein Error-Maß über error_value(scene) (isoliert selektiert, im Clip-Override)
               b) Lösche den Track mit maximalem Error (Operator delete_track im gültigen Override)
               c) Re-evaluiere aktuelle Markerzahl am Frame
      4) Weiter mit dem nächsten Frame der Rangliste.
    """
    scene = context.scene
    clip = _get_clip_from_context(context)
    if not clip:
        return {"status": "no_clip", "deleted_tracks": 0, "frames_processed": 0}

    base = int(scene.get(threshold_key, 20))
    threshold = max(0, base * 2)

    frames_sorted: List[Tuple[int, int]] = get_active_marker_counts_sorted(context)
    deleted_total = 0
    frames_processed = 0
    log = []

    for frame, count in frames_sorted:
        if count <= threshold:
            # ab hier sind alle folgenden Frames <= threshold (absteigend sortiert)
            break

        # Live-Recheck für aktuellen Frame
        active_pairs = _frame_active_markers(clip, frame)
        current_count = len(active_pairs)
        if current_count <= threshold:
            continue

        frames_processed += 1
        iteration = 0

        while current_count > threshold:
            iteration += 1

            candidate_tracks = [tr for (tr, _mk) in active_pairs]

            # Max-Error-Track bestimmen
            best_track = None
            best_error = None
            for tr in candidate_tracks:
                err = _compute_track_error_isolated(context, scene, tr)
                if err is None:
                    continue
                if (best_error is None) or (err > best_error):
                    best_error = err
                    best_track = tr

            if best_track is None:
                log.append(f"[Frame {frame}] Abbruch: kein Track-Error messbar.")
                break

            log.append(f"[Frame {frame}] Iter {iteration}: delete '{best_track.name}' (error={best_error:.6f})")

            if not dry_run:
                ok = _delete_track(context, best_track)
                if not ok:
                    log.append(f"[Frame {frame}] Löschen via Operator fehlgeschlagen.")
                    break
                deleted_total += 1

            # Re-Eval der aktiven Marker am selben Frame
            active_pairs = _frame_active_markers(clip, frame)
            current_count = len(active_pairs)

        log.append(f"[Frame {frame}] final_count={current_count}, threshold={threshold}")

    return {
        "status": "ok",
        "deleted_tracks": deleted_total,
        "frames_processed": frames_processed,
        "threshold": threshold,
        "log": log,
    }
