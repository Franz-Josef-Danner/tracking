# Helper/filter_tracks.py
# ------------------------------------------------------------
# Führt den Blender-internen Filter zur Track-Bereinigung aus
# und löscht Tracks unterhalb einer per UI gesetzten Mindestlänge.
# Jetzt mit detaillierten Logs zu Kandidaten & tatsächlich gelöschten Tracks.
# ------------------------------------------------------------

import bpy
from typing import Optional, Dict, List, Tuple


def _get_ui_min_frames(context: bpy.types.Context, fallback: int = 25) -> int:
    try:
        scene = context.scene
        if scene is None:
            raise AttributeError("context.scene is None")

        value = getattr(scene, "kaiserlich_frames_per_track", None)
        if value is None:
            print("[Kaiserlich Tracker][Filter] ⚠️ 'kaiserlich_frames_per_track' nicht gefunden – Fallback aktiv.")
            return int(fallback)

        ivalue = int(value)
        if ivalue < 0:
            print("[Kaiserlich Tracker][Filter] ⚠️ Negativer Wert erkannt – Fallback aktiv.")
            return int(fallback)
        return ivalue
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ⚠️ Fehler beim Lesen der UI-Frames-Property: {e} – Fallback {fallback}.")
        return int(fallback)


def _track_length_markers(track: "bpy.types.MovieTrackingTrack") -> int:
    """
    Heuristik: Anzahl Marker als Proxy für Track-Länge.
    Robust, unabhängig von Selektion/Visibility.
    """
    try:
        return len(track.markers)
    except Exception:
        return 0


def _snapshot_tracks(clip: "bpy.types.MovieClip") -> Dict[str, Tuple[int, str]]:
    """
    Erstellt eine Momentaufnahme aller Tracks im aktiven Tracking-Layer.
    Returns: {track_name: (marker_count, layer_name)}
    """
    result: Dict[str, Tuple[int, str]] = {}
    tracking = clip.tracking
    # Robust gegen Versionen/Setups ohne layers-API:
    if hasattr(tracking, "layers") and tracking.layers:
        for layer in tracking.layers:
            for t in layer.tracks:
                result[t.name] = (_track_length_markers(t), layer.name)
    else:
        # Fallback: direkte Trackliste
        for t in getattr(tracking, "tracks", []):
            result[t.name] = (_track_length_markers(t), "default")
    return result


def _classify_candidates(tracks_snapshot: Dict[str, Tuple[int, str]], min_frames: int) -> List[Tuple[str, int, str]]:
    """
    Ermittelt Kandidaten für das Löschen basierend auf Markeranzahl < min_frames.
    Returns: Liste von (track_name, marker_count, layer_name)
    """
    return [(n, cnt, layer) for n, (cnt, layer) in tracks_snapshot.items() if cnt < min_frames]


def filter_problematic_tracks(
    context: bpy.types.Context,
    threshold: float = 10.0,
) -> None:
    """
    Wendet den internen Bewegungs-Filter (clip.filter_tracks) ausschließlich
    anhand des Threshold-Werts an. Entfernt problematische Tracks direkt nach
    Fehlerwert, ohne Mindestlängen-Heuristik.

    Args:
        context: Blender Context (erwartet aktiven Movie Clip im Clip Editor).
        threshold: Fehler-Schwellenwert für problematische Tracks.
    """
    # Sicherstellen, dass wir im Movie Clip Editor sind
    space_data = getattr(context, "space_data", None)
    if not space_data or not hasattr(space_data, "clip") or space_data.clip is None:
        print("[Kaiserlich Tracker][Filter] ❌ Kein aktiver Movie Clip gefunden.")
        return

    clip = space_data.clip
    print(f"[Kaiserlich Tracker][Filter] Aktiver Clip: {clip.name}")

    # --- 1) Interner Filter (Bewegungsanalyse)
    try:
        bpy.ops.clip.filter_tracks(track_threshold=threshold)
        print(f"[Kaiserlich Tracker][Filter] Filter angewendet (Threshold={threshold}).")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Anwenden des Filters: {e}")
        return

    # --- 2) Threshold-basiertes Entfernen problematischer Tracks
    try:
        tracks = clip.tracking.tracks
        tracks_list = list(tracks)

        problematic = [
            t for t in tracks_list
            if hasattr(t, "average_error")
            and isinstance(t.average_error, (int, float))
            and t.average_error > threshold
        ]

        print(f"[Kaiserlich Tracker][Filter] Identified {len(problematic)} problematic tracks (> threshold={threshold}).")

        deleted = 0
        for t in problematic:
            try:
                tracks.remove(t)
                deleted += 1
            except Exception as e:
                print(f"[Kaiserlich Tracker][Filter] Entfernen fehlgeschlagen ({t.name}): {e}")

        print(f"[Kaiserlich Tracker][Filter] Removed {deleted} tracks (threshold-based).")
        print(f"[Kaiserlich Tracker][Filter] Übrig: {len(tracks)}")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Threshold-Cleanup: {e}")
        return
