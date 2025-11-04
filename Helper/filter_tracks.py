# Helper/filter_tracks.py
# ------------------------------------------------------------
# Führt den Blender-internen Filter zur Track-Bereinigung aus
# und löscht Tracks unterhalb einer per UI gesetzten Mindestlänge.
# Jetzt mit robustem CLIP_EDITOR-Kontext nach dem Schema aus filter_all_tracks.py.
# ------------------------------------------------------------

import bpy
from typing import Optional, Dict, List, Tuple

from .find_clip_editor_area import find_clip_editor_area  # wichtig: muss vorhanden sein

# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

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
    """Heuristik: Anzahl Marker als Proxy für Track-Länge."""
    try:
        return len(track.markers)
    except Exception:
        return 0


def _snapshot_tracks(clip: "bpy.types.MovieClip") -> Dict[str, Tuple[int, str]]:
    """Erstellt eine Momentaufnahme aller Tracks im aktiven Tracking-Layer."""
    result: Dict[str, Tuple[int, str]] = {}
    tracking = clip.tracking
    if hasattr(tracking, "layers") and tracking.layers:
        for layer in tracking.layers:
            for t in layer.tracks:
                result[t.name] = (_track_length_markers(t), layer.name)
    else:
        for t in getattr(tracking, "tracks", []):
            result[t.name] = (_track_length_markers(t), "default")
    return result


def _classify_candidates(tracks_snapshot: Dict[str, Tuple[int, str]], min_frames: int) -> List[Tuple[str, int, str]]:
    """Ermittelt Kandidaten für das Löschen basierend auf Markeranzahl < min_frames."""
    return [(n, cnt, layer) for n, (cnt, layer) in tracks_snapshot.items() if cnt < min_frames]


# ------------------------------------------------------------
# Hauptfunktion
# ------------------------------------------------------------

def filter_problematic_tracks(
    context: bpy.types.Context,
    threshold: float = 10.0,
) -> None:
    """
    Führt einen Filterdurchlauf durch und löscht Tracks über dem Reprojection-Threshold.
    Verwendet denselben stabilen Kontextaufbau wie filter_all_tracks.py.
    """
    space_data = getattr(context, "space_data", None)
    if not space_data or not hasattr(space_data, "clip") or space_data.clip is None:
        print("[Kaiserlich Tracker][Filter] ❌ Kein aktiver Movie Clip gefunden.")
        return

    clip = space_data.clip
    print(f"[Kaiserlich Tracker][Filter] Aktiver Clip: {clip.name}")

    # 1) Bewegungsanalyse
    try:
        bpy.ops.clip.filter_tracks(track_threshold=threshold)
        print(f"[Kaiserlich Tracker][Filter] Filter angewendet (Threshold={threshold}).")
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Anwenden des Filters: {e}")
        return

    # --- 2) Cleanup via clean_error (nur Kamera-Tracking)
    try:
        tracking = clip.tracking
        settings = tracking.settings
        settings.clean_action = 'DELETE_TRACK'
        settings.clean_error = float(threshold)
        settings.clean_frames = 0
    
        print(f"[Kaiserlich Tracker][Debug] clean_action=DELETE_TRACK, clean_error={settings.clean_error:.4f}, clean_frames={settings.clean_frames}")
        print("[Kaiserlich Tracker][Debug] Kamera-Tracking-Modus aktiv (kein Object-Tracking).")
    
        # Trackanzahl zählen
        def _count_tracks():
            try:
                return len(tracking.tracks)
            except Exception:
                return 0
    
        before = _count_tracks()
    
        # Kontext nach Schema aus filter_all_tracks.py aufbauen
        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            print("[Kaiserlich Tracker][Filter] ❌ Kein CLIP_EDITOR-Kontext auffindbar – clean_tracks nicht ausführbar.")
            return
    
        override = {
            "window": window,
            "screen": window.screen,
            "area": area,
            "region": region,
            "space_data": space,
        }
    
        print(f"[Kaiserlich Tracker][Debug] Context override: window={window}, area={area.type}, region={region.type}, edit_clip={clip.name}")
        
        # Cleanup ausführen (nur Kamera-Track) – stabiler Kontext mit temp_override
        with bpy.context.temp_override(
            window=window,
            area=area,
            region=region,
            space_data=space,
        ):
            result = bpy.ops.clip.clean_tracks(
                'EXEC_DEFAULT',
                frames=0,
                error=threshold,
                action='DELETE_TRACK'
            )

            if result != {'FINISHED'}:
                print(f"[Kaiserlich Tracker][Filter] ⚠️ bpy.ops.clip.clean_tracks result={result}")
    
        after = _count_tracks()
        deleted = max(0, before - after)
    
        print(f"[Kaiserlich Tracker][Filter] Cleanup ✓ (Camera) – gelöscht={deleted}, vorher={before}, übrig={after}, threshold={threshold:.4f}")
    
        if deleted == 0:
            print("[Kaiserlich Tracker][Debug] 0 gelöscht. Mögliche Ursachen:")
            print("  • Reprojection-Error nicht vorhanden bzw. <= threshold (prüfe nach Solve).")
            print("  • Solve / Reconstruction invalide oder noch nicht ausgeführt.")
            print("  • clean_error greift auf Layer ohne gültige Tracks.")
    
    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Cleanup (Camera): {e}")
