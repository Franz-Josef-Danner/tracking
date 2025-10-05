import bpy
from . import snapshot, delete

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
    new_tracks = [t for t in current_tracks if t.name not in prev_names]
    old_tracks = [t for t in current_tracks if t.name in prev_names]

    print(f'cleaneup: {len(new_tracks)} neue / {len(old_tracks)} alte Marker, md={md}')

    removed = 0
    for nt in new_tracks:
        nm_marker = _marker_at_frame(nt, frame_current)
        if nm_marker is None:
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
                print(f'cleaneup: disH {disH:.2f} < {md} -> remove {nt.name}')
                if delete.run(nt):
                    removed += 1
                delete_flag = True
                break
            elif disV < md:
                print(f'cleaneup: disV {disV:.2f} < {md} -> remove {nt.name}')
                if delete.run(nt):
                    removed += 1
                delete_flag = True
                break
        if not delete_flag:
            print(f'cleaneup: keep {nt.name}')

    print(f'cleaneup: entfernt {removed} Marker')