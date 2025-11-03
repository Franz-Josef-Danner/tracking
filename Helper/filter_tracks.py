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
    for layer in tracking.layers:
        for t in layer.tracks:
            result[t.name] = (_track_length_markers(t), layer.name)
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
    min_frames: Optional[int] = None,
) -> None:
    """
    1) Wendet den internen Bewegungs-Filter an (clip.filter_tracks).
    2) Führt ein Cleanup aus und löscht Tracks, die kürzer sind als
       die in der UI definierte Mindestlänge (Frames per Track).

    Args:
        context: Blender Context (erwartet aktiven Movie Clip im Clip Editor).
        threshold: Threshold für den internen Filter.
        min_frames: Optional manuell vorgeben; wenn None, wird aus UI gelesen.
    """
    # Sicherstellen, dass wir im Movie Clip Editor sind
    space_data = getattr(context, "space_data", None)
    if not space_data or not hasattr(space_data, "clip") or space_data.clip is None:
        print("[Kaiserlich Tracker][Filter] ❌ Kein aktiver Movie Clip gefunden.")
        return

    clip = space_data.clip
    print(f"[Kaiserlich Tracker][Filter] Aktiver Clip: {clip.name}")

    # --- 0) UI-Wert für min_frames auflösen (falls nicht manuell gesetzt)
    resolved_min_frames = _get_ui_min_frames(context, fallback=25) if min_frames is None else int(min_frames)
    print(f"[Kaiserlich Tracker][Filter] Using min_frames={resolved_min_frames} (Quelle: {'UI' if min_frames is None else 'Param'})")

    # --- 1) Interner Filter (Bewegungsanalyse)
    try:
        bpy.ops.clip.filter_tracks(track_threshold=threshold)
        print(f"[Kaiserlich Tracker][Filter] Filter angewendet (Threshold={threshold}).")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Anwenden des Filters: {e}")
        return

    # --- 1.5) Snapshot & Vorab-Analyse (für Logging/Audit)
    try:
        before_snapshot = _snapshot_tracks(clip)
        total_before = len(before_snapshot)
        candidates = _classify_candidates(before_snapshot, resolved_min_frames)

        print(f"[Kaiserlich Tracker][Filter] Vorab-Analyse: {len(candidates)}/{total_before} Tracks < {resolved_min_frames} Frames (Markeranzahl-Heuristik).")
        if candidates:
            print("[Kaiserlich Tracker][Filter] Kandidaten (Name | Layer | Marker):")
            for name, cnt, layer in sorted(candidates, key=lambda x: (x[2], x[0])):
                print(f"  - {name} | {layer} | {cnt}")
        else:
            print("[Kaiserlich Tracker][Filter] Keine Kandidaten unterhalb der Mindestlänge identifiziert.")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ⚠️ Vorab-Analyse fehlgeschlagen: {e}")

    # --- 2) Cleanup für kurze Tracks
    try:
        tracking_settings = clip.tracking.settings
        tracking_settings.clean_action = 'DELETE_TRACK'  # Alternativen: 'SELECT', 'DELETE_SEGMENTS'
        tracking_settings.clean_error = 0.0              # nur Frames-Kriterium nutzen
        tracking_settings.clean_frames = resolved_min_frames

        bpy.ops.clip.clean_tracks()
        print(f"[Kaiserlich Tracker][Filter] Cleanup ✓ – Tracks mit < {resolved_min_frames} Frames gelöscht.")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Cleanup: {e}")
        return

    # --- 2.5) Nachher-Snapshot & Verifikation
    try:
        after_snapshot = _snapshot_tracks(clip)
        remaining_names = set(after_snapshot.keys())
        candidate_names = {n for (n, _, _) in candidates}
        actually_deleted = sorted(list(candidate_names - remaining_names))
        survived_candidates = sorted(list(candidate_names & remaining_names))

        print(f"[Kaiserlich Tracker][Filter] Verifikation:")
        print(f"  - Tracks vor Cleanup: {total_before}")
        print(f"  - Gelöscht (erwartet < {resolved_min_frames}): {len(actually_deleted)}")
        if actually_deleted:
            print("  - Gelöschte Tracks:")
            for n in actually_deleted:
                cnt, layer = before_snapshot.get(n, (None, "?"))
                print(f"      • {n} | {layer} | vorher Marker={cnt}")

        if survived_candidates:
            print(f"  - Nicht gelöscht, obwohl Kandidat: {len(survived_candidates)}")
            print("    (Blender-Clean kann Segmentlogik nutzen; Marker≈Frames ist eine Näherung.)")
            for n in survived_candidates:
                before_cnt, layer = before_snapshot.get(n, (None, "?"))
                after_cnt = after_snapshot.get(n, (None, "?"))[0] if n in after_snapshot else None
                print(f"      • {n} | {layer} | vorher Marker={before_cnt} | nachher Marker={after_cnt}")

        print(f"[Kaiserlich Tracker][Filter] Tracks nach Cleanup: {len(after_snapshot)} (Δ={len(after_snapshot)-total_before})")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ⚠️ Verifikations-Logging fehlgeschlagen: {e}")
