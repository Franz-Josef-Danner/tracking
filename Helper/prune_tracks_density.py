# Datei-Vorschlag: Helper/prune_tracks_by_marker_density.py

import bpy
from typing import List, Tuple, Optional

# Erwartet: Du hast in Helper/find_max_marker_frame.py eine Zählfunktion.
# Falls dein Modul anders heißt, bitte den Import entsprechend anpassen.
from .find_max_marker_frame import get_active_marker_counts_sorted  # (context) -> List[(frame, count)]
from .error_value import error_value  # nutzt selektierte Tracks, berechnet StdAbw X+Y

def _get_clip_from_context(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    # robust: erst aktiven CLIP_EDITOR durchsuchen, dann space_data Fallback
    screen = getattr(context, "screen", None)
    if screen:
        for a in screen.areas:
            if a.type == 'CLIP_EDITOR':
                sp = a.spaces.active
                clip = getattr(sp, "clip", None)
                if clip:
                    return clip
    space = getattr(context, "space_data", None)
    return getattr(space, "clip", None) if space else None


def _frame_active_markers(clip: bpy.types.MovieClip, frame: int) -> List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingMarker]]:
    """Liefert Liste (Track, Marker) aller *aktiven* Marker auf genau diesem Frame."""
    out = []
    for tr in clip.tracking.tracks:
        if getattr(tr, "mute", False):
            continue
        mk = tr.markers.find_frame(frame)
        if not mk:
            continue
        if getattr(mk, "mute", False):
            continue
        out.append((tr, mk))
    return out


def _compute_track_error_isolated(scene: bpy.types.Scene, track: bpy.types.MovieTrackingTrack) -> Optional[float]:
    """
    Nutzt dein bestehendes error_value(scene), das über *selektierte* Marker rechnet.
    Wir selektieren transient GENAU diesen Track, rufen error_value() auf und restoren Selektion.
    """
    clip = bpy.context.space_data.clip if bpy.context.space_data else None
    if clip is None:
        return None

    # Selektion sichern
    prev_selection = {t.name: bool(t.select) for t in clip.tracking.tracks}
    try:
        # Nur den Ziel-Track selektieren
        for t in clip.tracking.tracks:
            t.select = (t == track)
        # Fehlermaß berechnen (StdAbw X + StdAbw Y über Marker des Tracks)
        val = error_value(scene)
        return float(val) if val is not None else None
    finally:
        # Selektion wiederherstellen
        for t in clip.tracking.tracks:
            t.select = prev_selection.get(t.name, False)


def _remove_track(clip: bpy.types.MovieClip, track: bpy.types.MovieTrackingTrack) -> None:
    """
    Löscht den Track stabil via RNA, ohne Operator-Kontextabhängigkeit.
    """
    try:
        clip.tracking.tracks.remove(track)
    except RuntimeError:
        # Fallback: falls remove fehlschlägt, versuche über Operator (benötigt gültigen Override)
        bpy.ops.clip.delete_track()  # nur wenn Track selektiert; hier bewusst *nicht* automatisch selektieren
        # Wird bewusst nicht „smart“ gemacht, um UI-Bindungen zu vermeiden.


def prune_tracks_hierarchically_by_marker_density(
    context: bpy.types.Context,
    *,
    threshold_key: str = "marker_frame",    # Ziel: auf jedem Frame auf <= scene[threshold_key] * 2 Marker eindampfen
    prefer_earliest_on_tie: bool = True,    # nur relevant, falls deine Sortierung Gleichstände auflöst
    dry_run: bool = False,                  # nur analysieren, nicht löschen
) -> dict:
    """
    Pipeline:
      1) Hole sortierte Liste (frame, count) aus get_active_marker_counts_sorted(context), absteigend.
      2) Definiere Threshold = scene[threshold_key] * 2 (Default: 20*2, falls Key fehlt).
      3) Für jeden Frame mit count > Threshold:
           - Ermittele aktive Marker/Tracks am Frame
           - Solange aktuelle Markermenge > Threshold:
               a) Bestimme pro Track ein Error-Maß über error_value(scene) (isoliert selektiert)
               b) Lösche den Track mit maximalem Error
               c) Re-evaluiere aktuelle Markerzahl am Frame
      4) Weiter mit dem nächsten Frame der Rangliste.
    Rückgabe: Summary-Dict mit Statistik.
    """
    scene = context.scene
    clip = _get_clip_from_context(context)
    if not clip:
        return {"status": "no_clip", "deleted_tracks": 0, "frames_processed": 0}

    base = int(scene.get(threshold_key, 20))
    threshold = max(0, base * 2)

    # Absteigende Liste (frame,count); bei Gleichstand frühester Frame zuerst
    frames_sorted: List[Tuple[int, int]] = get_active_marker_counts_sorted(context)
    deleted_total = 0
    frames_processed = 0
    log = []

    for frame, count in frames_sorted:
        if count <= threshold:
            # ab hier sind alle folgenden Frames <= threshold (weil absteigend sortiert)
            break

        # Re-Check live (Liste könnte nach Löschungen veralten)
        active_pairs = _frame_active_markers(clip, frame)
        current_count = len(active_pairs)

        if current_count <= threshold:
            continue

        frames_processed += 1
        iteration = 0

        while current_count > threshold:
            iteration += 1

            # Kandidaten-Tracks am aktuellen Frame (aktiv)
            candidate_tracks = [tr for (tr, mk) in active_pairs]

            # Error pro Track ermitteln (isoliert via selection → error_value(scene))
            best_track = None
            best_error = None

            for tr in candidate_tracks:
                err = _compute_track_error_isolated(scene, tr)
                if err is None:
                    continue
                if (best_error is None) or (err > best_error):
                    best_error = err
                    best_track = tr

            if best_track is None:
                # keine valide Fehlermessung → zur Sicherheit abbrechen, sonst Endlosschleife
                log.append(f"[Frame {frame}] Abbruch: kein track error messbar.")
                break

            # Delete-Kandidat steht fest
            log.append(f"[Frame {frame}] Iter {iteration}: remove track '{best_track.name}' (error={best_error:.6f})")

            if not dry_run:
                _remove_track(clip, best_track)
                deleted_total += 1

            # Re-Evaluierung: aktuelle Marker am Frame neu bestimmen
            active_pairs = _frame_active_markers(clip, frame)
            current_count = len(active_pairs)

        # Ende pro Frame
        log.append(f"[Frame {frame}] final_count={current_count}, threshold={threshold}")

    return {
        "status": "ok",
        "deleted_tracks": deleted_total,
        "frames_processed": frames_processed,
        "threshold": threshold,
        "log": log,
    }
