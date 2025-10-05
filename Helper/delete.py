import bpy


def _resolve_track(context, track_name: str):
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print(f"[Kaiserlich Tracker][DEBUG] _resolve_track: Kein gültiger CLIP_EDITOR Kontext (space={getattr(space, 'type', None)})")
        return None
    clip = getattr(space, 'clip', None)
    if not clip:
        print("[Kaiserlich Tracker][DEBUG] _resolve_track: Kein aktiver Clip vorhanden.")
        return None
    tracking = clip.tracking
    # Falls Track nicht gefunden wird, später Liste ausgeben
    for tr in tracking.tracks:
        if tr.name == track_name:
            return tr
    print(f"[Kaiserlich Tracker][DEBUG] _resolve_track: Track '{track_name}' nicht gefunden. Verfügbare Tracks: {[t.name for t in tracking.tracks]}")
    return None


def _marker_frames(track):
    try:
        return sorted([m.frame for m in track.markers])
    except Exception:
        return []


def _remove_marker_object(track, marker):
    """Versucht verschiedene API-Varianten zum Entfernen eines Marker-Objekts.
    Rückgabe: (removed: bool, methode: str oder None)"""
    if marker is None:
        return False, None

    # Wir protokollieren explizit welche Methoden existieren
    available = [m for m in ("delete", "remove", "delete_frame") if hasattr(track.markers, m)]
    print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: Verfügbare Methoden={available} Track={track.name} MarkerFrame={getattr(marker,'frame',None)}")

    # Variante 1: delete(marker)
    if hasattr(track.markers, 'delete'):
        try:
            track.markers.delete(marker)
            print("[Kaiserlich Tracker][DEBUG] _remove_marker_object: delete(marker) OK")
            return True, 'delete(marker)'
        except Exception as e:
            print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: delete(marker) FAIL -> {e}")

    # Variante 2: remove(marker)
    if hasattr(track.markers, 'remove'):
        try:
            track.markers.remove(marker)
            print("[Kaiserlich Tracker][DEBUG] _remove_marker_object: remove(marker) OK")
            return True, 'remove(marker)'
        except Exception as e:
            print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: remove(marker) FAIL -> {e}")

    # Variante 3: delete_frame(frame)
    if hasattr(track.markers, 'delete_frame') and hasattr(marker, 'frame'):
        try:
            track.markers.delete_frame(marker.frame)
            print("[Kaiserlich Tracker][DEBUG] _remove_marker_object: delete_frame(frame) OK")
            return True, 'delete_frame(frame)'
        except Exception as e:
            print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: delete_frame(frame) FAIL -> {e}")

    print("[Kaiserlich Tracker][DEBUG] _remove_marker_object: Keine Methode hat funktioniert.")
    return False, None


def delete_marker_frame(context, track_name: str, frame: int) -> bool:
    """Löscht einen einzelnen Marker-Keyframe eines Tracks (by frame) mit ausführlichem Debug-Log."""
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print("[Kaiserlich Tracker] delete_marker_frame: Kein CLIP_EDITOR Kontext.")
        return False
    clip = getattr(space, 'clip', None)
    if not clip:
        print("[Kaiserlich Tracker] delete_marker_frame: Kein aktiver Clip.")
        return False
    tracking = clip.tracking
    print(f"[Kaiserlich Tracker][DEBUG] delete_marker_frame: Ziel track='{track_name}' frame={frame} AktuelleSceneFrame={context.scene.frame_current}")
    print(f"[Kaiserlich Tracker][DEBUG] delete_marker_frame: Verfügbare Tracks={[t.name for t in tracking.tracks]}")
    try:
        for tr in tracking.tracks:
            if tr.name != track_name:
                continue
            frames_vorher = _marker_frames(tr)
            print(f"[Kaiserlich Tracker][DEBUG] Track '{tr.name}' MarkerFrames vor Löschung: {frames_vorher[:50]} (Total={len(frames_vorher)})")

            # Marker suchen
            marker = None
            used_find = False
            if hasattr(tr.markers, 'find_frame'):
                try:
                    marker = tr.markers.find_frame(frame)
                    used_find = True
                except Exception as e:
                    print(f"[Kaiserlich Tracker][DEBUG] find_frame Exception -> {e}")
                    marker = None
            if marker is None:
                for m in tr.markers:
                    if getattr(m, 'frame', None) == frame:
                        marker = m
                        break
            if marker is None:
                print(f"[Kaiserlich Tracker] Marker nicht gefunden: track={track_name} frame={frame} (find_frame_verwendet={used_find})")
                return False
            print(f"[Kaiserlich Tracker][DEBUG] Gefundener Marker frame={getattr(marker,'frame',None)} used_find={used_find}")

            removed, methode = _remove_marker_object(tr, marker)
            print(f"[Kaiserlich Tracker][DEBUG] Entfernen Ergebnis removed={removed} methode={methode}")

            # Verifikation
            still_there = any(m.frame == frame for m in tr.markers)
            frames_nachher = _marker_frames(tr)
            print(f"[Kaiserlich Tracker][DEBUG] Track '{tr.name}' MarkerFrames nach Löschung: {frames_nachher[:50]} (Total={len(frames_nachher)})")

            if not still_there and removed:
                try:
                    context.scene.frame_set(context.scene.frame_current)
                except Exception as e:
                    print(f"[Kaiserlich Tracker][DEBUG] frame_set Exception -> {e}")
                print(f"[Kaiserlich Tracker] Marker gelöscht: track={track_name} frame={frame} via {methode}")
                return True
            else:
                print(f"[Kaiserlich Tracker] Marker konnte nicht gelöscht werden (track={track_name} frame={frame}) removed={removed} still_there={still_there} methode={methode}")
                # Zusätzliche Diagnose: existiert ein Marker in der Nähe?
                if frames_nachher:
                    # Nächster Frame Unterschied
                    diffs = [(abs(f - frame), f) for f in frames_nachher]
                    diffs.sort()
                    print(f"[Kaiserlich Tracker][DEBUG] Nächste vorhandene Markerframes relativ zum Ziel: {diffs[:5]}")
                return False
    except Exception as e:
        print(f"[Kaiserlich Tracker] Fehler beim Löschen Marker track={track_name} frame={frame}: {e}")
    return False


def delete_marker_index(context, track_name: str, index: int) -> bool:
    """Löscht Marker per Index (0-basiert in aktueller Reihenfolge der Collection) mit Debug."""
    tr = _resolve_track(context, track_name)
    if not tr:
        print(f"[Kaiserlich Tracker] Track nicht gefunden: {track_name}")
        return False
    markers_list = list(tr.markers)
    print(f"[Kaiserlich Tracker][DEBUG] delete_marker_index: Track={track_name} MarkerAnzahl={len(markers_list)} IndexZiel={index}")
    if index < 0 or index >= len(markers_list):
        print(f"[Kaiserlich Tracker] Ungültiger Marker-Index {index} (Track {track_name})")
        return False
    marker = markers_list[index]
    frame = getattr(marker, 'frame', None)
    removed, methode = _remove_marker_object(tr, marker)
    still_there = any(getattr(m, 'frame', None) == frame for m in tr.markers)
    if removed and not still_there:
        print(f"[Kaiserlich Tracker] Marker (Index {index}, Frame {frame}) gelöscht: {track_name} via {methode}")
        return True
    print(f"[Kaiserlich Tracker] Marker (Index {index}) NICHT gelöscht: {track_name} removed={removed} still_there={still_there} methode={methode}")
    return False


def delete_all_markers(context, track_name: str) -> int:
    """Löscht alle Marker eines Tracks und gibt Anzahl gelöschter Marker zurück (Debug)."""
    tr = _resolve_track(context, track_name)
    if not tr:
        print(f"[Kaiserlich Tracker] Track nicht gefunden: {track_name}")
        return 0
    original = _marker_frames(tr)
    print(f"[Kaiserlich Tracker][DEBUG] delete_all_markers: Track={track_name} StartFrames={original[:50]} Total={len(original)}")
    count = 0
    for mk in list(tr.markers):
        removed, methode = _remove_marker_object(tr, mk)
        if removed:
            count += 1
    remaining = _marker_frames(tr)
    print(f"[Kaiserlich Tracker] Alle Marker gelöscht: {track_name} (Entfernt={count} Vorher={len(original)} Rest={len(remaining)})")
    if remaining:
        print(f"[Kaiserlich Tracker][DEBUG] Verbliebene Frames: {remaining[:50]}")
    return count
