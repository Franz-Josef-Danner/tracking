import bpy
from . import snapshot, delete, bulk_delete

def _marker_at_frame(track, frame_current):
    # Finde Marker exakt auf aktuellem Frame, sonst None
    for m in track.markers:
        if m.frame == frame_current:
            return m
    return None

def run(context, values: dict):
    """Bereinigt neu angelegte Marker, die zu nahe an bestehenden liegen.

    Algorithmus gemäß Vorgabe:
      Für jeden neuen Marker (NM) vergleiche mit allen alten Markern (AMA):
        - Koordinaten (normalized) * Auflösung -> Pixelpositionen
        - disH = |x_old - x_new|, disV = |y_old - y_new|
        - Wenn disH < md -> neuer Marker wird gelöscht
          Sonst wenn disV < md -> neuer Marker wird gelöscht
          Sonst bleibt er erhalten
    """
    clip = bpy.context.edit_movieclip
    if not clip:
        print('cleaneup: kein Clip')
        return

    md = values.get('md')
    hz = values.get('hz')
    vc = values.get('vc')
    frame_current = context.scene.frame_current

    prev_names = snapshot.get_previous_for_clip(clip)
    current_tracks = list(clip.tracking.tracks)
    new_tracks = [t for t in current_tracks if t.name not in prev_names and not t.name.startswith('DELETED_')]
    old_tracks = [t for t in current_tracks if t.name in prev_names and not t.name.startswith('DELETED_')]

    print(f'cleaneup: {len(new_tracks)} neue / {len(old_tracks)} alte Marker, md={md}')

    removed = 0
    # Sammeln statt sofort löschen – dann ein Operator-Aufruf.
    to_delete_tracks = []
    for nt in new_tracks:
        nm_marker = _marker_at_frame(nt, frame_current)
        if nm_marker is None:
            try:
                # Log alle Frames des Tracks
                frames_list = [m.frame for m in nt.markers]
                print(f'cleaneup: kein Marker auf Frame {frame_current} in {nt.name} (Frames={frames_list})')
            except Exception:
                pass
            continue
        # Normalized zu Pixel
        nm_x = nm_marker.co[0] * hz
        nm_y = nm_marker.co[1] * vc
        delete_flag = False
        for ot in old_tracks:
            om = _marker_at_frame(ot, frame_current)
            if om is None:
                continue
            om_x = om.co[0] * hz
            om_y = om.co[1] * vc
            disH = abs(om_x - nm_x)
            disV = abs(om_y - nm_y)
            if disH < md:
                print(f'cleaneup: disH {disH:.2f} < {md} -> flag remove {nt.name}')
                to_delete_tracks.append(nt)
                delete_flag = True
                break
            elif disV < md:
                print(f'cleaneup: disV {disV:.2f} < {md} -> flag remove {nt.name}')
                to_delete_tracks.append(nt)
                delete_flag = True
                break
        if not delete_flag:
            print(f'cleaneup: keep {nt.name}')

    # Jetzt gesammelt löschen
    if to_delete_tracks:
        print(f'cleaneup: versuche {len(to_delete_tracks)} Tracks via bulk_delete zu entfernen')
        actually_removed = bulk_delete.delete_tracks(to_delete_tracks)
        removed += actually_removed
    else:
        print('cleaneup: keine Tracks zum Löschen geflaggt')

    # Statistik nach Bereinigung
    try:
        remaining = [t.name for t in clip.tracking.tracks]
        print(f'cleaneup: entfernt {removed} Tracks – verbleibende Tracks: {remaining}')
    except Exception:
        print(f'cleaneup: entfernt {removed} Tracks')