import bpy
from . import snapshot, delete, bulk_delete
import time

# Konfiguration für Stabilität
_BULK_CHUNK_SIZE = 4          # In kleineren Gruppen löschen um UI-Block zu reduzieren
_RETRY_ON_FAIL = 1            # Wie oft eine fehlgeschlagene Gruppe nochmals versucht wird
_DELETE_STRATEGY = 'temp_first'  # 'auto' | 'temp_first' | 'operator_first'
_GLOBAL_TIMEOUT_SEC = 5       # Harte Obergrenze für gesamten Cleanup-Löschteil

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
        print(f'cleaneup: versuche {len(to_delete_tracks)} Tracks via bulk_delete (Strategie={_DELETE_STRATEGY}) zu entfernen')
        start_delete = time.perf_counter()
        # In Chunks verarbeiten
        for i in range(0, len(to_delete_tracks), _BULK_CHUNK_SIZE):
            if (time.perf_counter() - start_delete) > _GLOBAL_TIMEOUT_SEC:
                print('cleaneup: Lösch-Timeout erreicht – breche weitere Versuche ab')
                break
            chunk = to_delete_tracks[i:i+_BULK_CHUNK_SIZE]
            attempt = 0
            while True:
                attempt += 1
                before_names = [t.name for t in chunk]
                print(f'cleaneup: Chunk {i//_BULK_CHUNK_SIZE+1} Versuch {attempt} Tracks={before_names}')
                removed_now = bulk_delete.delete_tracks(chunk, strategy=_DELETE_STRATEGY)
                removed += removed_now
                # Herausfiltern was noch existiert (nicht physisch gelöscht) aber nicht logisch umbenannt
                remaining_obj = []
                current_names = {t.name: t for t in bpy.context.edit_movieclip.tracking.tracks}
                for t in chunk:
                    if t.name in current_names and not t.name.startswith('DELETED_'):
                        remaining_obj.append(current_names[t.name])
                if not remaining_obj:
                    break  # Alles erledigt (physisch oder logical)
                if removed_now == 0 and attempt > _RETRY_ON_FAIL:
                    print('cleaneup: keine weitere Verbesserung – breche Chunk ab')
                    break
                if (time.perf_counter() - start_delete) > _GLOBAL_TIMEOUT_SEC:
                    print('cleaneup: Timeout während Chunk – Abbruch')
                    break
    else:
        print('cleaneup: keine Tracks zum Löschen geflaggt')

    # Statistik nach Bereinigung
    try:
        remaining = [t.name for t in clip.tracking.tracks]
        print(f'cleaneup: entfernt {removed} Tracks – verbleibende Tracks: {remaining}')
    except Exception:
        print(f'cleaneup: entfernt {removed} Tracks')