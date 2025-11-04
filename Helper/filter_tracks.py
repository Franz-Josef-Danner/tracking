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
    Wendet den internen Bewegungs-Filter (clip.filter_tracks) an und löscht
    anschließend alle Tracks mit einem Reprojektion-Error größer als threshold.
    Nutzt dafür die offizielle Blender-API (clean_error) anstelle manueller
    Remove-Aufrufe – robust gegenüber Layer-Setups.

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

    # --- 2) Cleanup via clean_error (Operator, korrekter Kontext)
    try:
        tracking = clip.tracking
        settings = tracking.settings
        settings.clean_action = 'DELETE_TRACK'
        settings.clean_error  = float(threshold)
        settings.clean_frames = 0

        # Sanity-Log
        print(f"[Kaiserlich Tracker][Debug] clean_action=DELETE_TRACK, clean_error={settings.clean_error:.4f}, clean_frames={settings.clean_frames}")

        # Relevantes Tracking-Objekt (nur Log, Operator nutzt Scene/Context)
        active_obj = getattr(tracking, "active_object", None)
        if active_obj:
            print(f"[Kaiserlich Tracker][Debug] Active tracking object: {active_obj.name} ({len(active_obj.tracks)} Tracks)")
        else:
            print("[Kaiserlich Tracker][Debug] Warnung: Kein active_object gefunden.")

        # Einen gültigen CLIP_EDITOR-Kontext erzwingen (Area/Region/Window + edit_clip)
        win = None
        area = None
        region = None
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == 'CLIP_EDITOR':
                    # Bevorzugt die WINDOW-Region
                    reg = next((r for r in a.regions if r.type == 'WINDOW'), None)
                    if reg is not None:
                        win, area, region = w, a, reg
                        break
            if win:
                break

        if not (win and area and region):
            print("[Kaiserlich Tracker][Filter] ❌ Kein CLIP_EDITOR-Kontext auffindbar – clean_tracks nicht ausführbar.")
            print("→ Öffne einen Movie Clip Editor (Area.type='CLIP_EDITOR') oder führe im Tracking-Workspace aus.")
            return

        # Vorher/Nachher zählen (über aktives Objekt, falls vorhanden; sonst Gesamtliste)
        def _count_tracks():
            try:
                if active_obj and getattr(active_obj, 'tracks', None) is not None:
                    return len(active_obj.tracks)
            except Exception:
                pass
            try:
                return len(tracking.tracks)
            except Exception:
                return 0

        before = _count_tracks()

        # temp_override ist der korrekte Weg ab Blender 4.x
        # Wichtig: edit_clip muss gesetzt sein.
        print(f"[Kaiserlich Tracker][Debug] Context override: window={win}, area={area.type}, region={region.type}, edit_clip={clip.name}")
        try:
            ctx = bpy.context
            # Ab Blender 4.x vorhanden; in 3.6 ebenfalls (Backport).
            with ctx.temp_override(window=win, area=area, region=region, edit_clip=clip):
                # EXEC_DEFAULT erzwingt direkten Operatorlauf ohne UI-Invoke
                bpy.ops.clip.clean_tracks('EXEC_DEFAULT')
        except AttributeError:
            # Fallback für sehr alte Builds ohne temp_override (unwahrscheinlich)
            override = {'window': win, 'screen': win.screen, 'area': area, 'region': region, 'edit_clip': clip}
            bpy.ops.clip.clean_tracks('EXEC_DEFAULT', override)

        after = _count_tracks()
        deleted = max(0, before - after)
        print(f"[Kaiserlich Tracker][Filter] Cleanup ✓ (clean_error) – gelöscht={deleted}, vorher={before}, übrig={after}, threshold={threshold:.4f}")

        if deleted == 0:
            print("[Kaiserlich Tracker][Debug] 0 gelöscht. Mögliche Ursachen:")
            print("  • Reprojection-Error nicht vorhanden bzw. <= threshold (prüfe nach Solve).")
            print("  • Solve / Reconstruction fehlte oder ist invalide (recon.is_valid == False).")
            print("  • clean_error greift auf anderes Objekt/Layer als erwartet – prüfe active_object und Clip.")

    except Exception as e:
        print(f"[Kaiserlich Tracker][Filter] ❌ Fehler beim Cleanup über clean_error: {e}")
