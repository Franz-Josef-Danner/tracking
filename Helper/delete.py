import bpy


def _resolve_track(context, track_name: str):
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        return None
    clip = getattr(space, 'clip', None)
    if not clip:
        return None
    tracking = clip.tracking
    for tr in tracking.tracks:
        if tr.name == track_name:
            return tr
    return None


def _remove_marker_object(track, marker) -> bool:
    """Versucht verschiedene API-Varianten zum Entfernen eines Marker-Objekts.
    Gibt True zurück, falls entfernt."""
    removed = False
    if marker is None:
        return False
    # Variante 1
    if hasattr(track.markers, 'delete') and not removed:
        try:
            track.markers.delete(marker)
            removed = True
        except Exception:
            pass
    # Variante 2
    if hasattr(track.markers, 'remove') and not removed:
        try:
            track.markers.remove(marker)
            removed = True
        except Exception:
            pass
    # Variante 3 (per frame)
    if hasattr(track.markers, 'delete_frame') and not removed:
        try:
            track.markers.delete_frame(marker.frame)
            removed = True
        except Exception:
            pass
    return removed


def delete_marker_frame(context, track_name: str, frame: int) -> bool:
    """Löscht einen einzelnen Marker-Keyframe eines Tracks (by frame)."""
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print("[Kaiserlich Tracker] delete_marker_frame: Kein CLIP_EDITOR Kontext.")
        return False
    clip = getattr(space, 'clip', None)
    if not clip:
        print("[Kaiserlich Tracker] delete_marker_frame: Kein aktiver Clip.")
        return False
    tracking = clip.tracking
    try:
        for tr in tracking.tracks:
            if tr.name != track_name:
                continue
            # Marker suchen
            marker = None
            try:
                if hasattr(tr.markers, 'find_frame'):
                    marker = tr.markers.find_frame(frame)
            except Exception:
                marker = None
            if marker is None:
                for m in tr.markers:
                    if getattr(m, 'frame', None) == frame:
                        marker = m
                        break
            if marker is None:
                print(f"[Kaiserlich Tracker] Marker nicht gefunden: track={track_name} frame={frame}")
                return False
            removed = _remove_marker_object(tr, marker)

            # Verifikation
            still_there = False
            for m in tr.markers:
                if m.frame == frame:
                    still_there = True
                    break

            if not still_there and removed:
                # UI/Depsgraph Update forcieren
                try:
                    context.scene.frame_set(context.scene.frame_current)
                except Exception:
                    pass
                print(f"[Kaiserlich Tracker] Marker gelöscht: track={track_name} frame={frame}")
                return True
            else:
                print(f"[Kaiserlich Tracker] Marker konnte nicht gelöscht werden (track={track_name} frame={frame})")
                return False
    except Exception as e:
        print(f"[Kaiserlich Tracker] Fehler beim Löschen Marker track={track_name} frame={frame}: {e}")
    return False


def delete_marker_index(context, track_name: str, index: int) -> bool:
    """Löscht Marker per Index (0-basiert in aktueller Reihenfolge der Collection)."""
    tr = _resolve_track(context, track_name)
    if not tr:
        print(f"[Kaiserlich Tracker] Track nicht gefunden: {track_name}")
        return False
    markers_list = list(tr.markers)
    if index < 0 or index >= len(markers_list):
        print(f"[Kaiserlich Tracker] Ungültiger Marker-Index {index} (Track {track_name})")
        return False
    marker = markers_list[index]
    frame = getattr(marker, 'frame', None)
    removed = _remove_marker_object(tr, marker)
    if removed:
        try:
            tr.markers.find_frame(frame)  # verifizieren falls API vorhanden
            # wenn noch vorhanden -> nicht erfolgreich
        except Exception:
            pass
        print(f"[Kaiserlich Tracker] Marker (Index {index}, Frame {frame}) gelöscht: {track_name}")
        return True
    print(f"[Kaiserlich Tracker] Marker (Index {index}) NICHT gelöscht: {track_name}")
    return False


def delete_all_markers(context, track_name: str) -> int:
    """Löscht alle Marker eines Tracks und gibt Anzahl gelöschter Marker zurück."""
    tr = _resolve_track(context, track_name)
    if not tr:
        print(f"[Kaiserlich Tracker] Track nicht gefunden: {track_name}")
        return 0
    count = 0
    # Kopie, damit während Löschung iterierbar bleibt
    for mk in list(tr.markers):
        if _remove_marker_object(tr, mk):
            count += 1
    print(f"[Kaiserlich Tracker] Alle Marker gelöscht: {track_name} (Anzahl={count})")
    return count
