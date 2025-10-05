import bpy


def delete_marker_frame(context, track_name: str, frame: int) -> bool:
    """Löscht einen einzelnen Marker-Keyframe eines Tracks robust.

    Versucht mehrere Varianten (API kann je Blender-Version differieren):
      1. markers.find_frame(frame) + markers.delete(marker)
      2. markers.remove(marker)
      3. markers.delete_frame(frame)
    Anschließend Verifikation: existiert der Frame noch?
    """
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
            # Marker suchen (Fallback falls find_frame nicht existiert / None liefert)
            marker = None
            if hasattr(tr.markers, 'find_frame'):
                try:
                    marker = tr.markers.find_frame(frame)
                except Exception:
                    marker = None
            if marker is None:
                # manueller Scan
                for m in tr.markers:
                    if m.frame == frame:
                        marker = m
                        break
            if marker is None:
                print(f"[Kaiserlich Tracker] Marker nicht gefunden: track={track_name} frame={frame}")
                return False

            removed = False
            # Variante 1: delete(marker)
            if hasattr(tr.markers, 'delete'):
                try:
                    tr.markers.delete(marker)
                    removed = True
                except Exception:
                    pass
            # Variante 2: remove(marker)
            if not removed and hasattr(tr.markers, 'remove'):
                try:
                    tr.markers.remove(marker)
                    removed = True
                except Exception:
                    pass
            # Variante 3: delete_frame(frame)
            if not removed and hasattr(tr.markers, 'delete_frame'):
                try:
                    tr.markers.delete_frame(frame)
                    removed = True
                except Exception:
                    pass

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
