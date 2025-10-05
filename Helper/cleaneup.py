import bpy
from . import snapshot, delete, bulk_delete
import time

# Schlanke Konfiguration
_BULK_CHUNK_SIZE = 4      # Chunk-Größe für Löschdurchläufe
_RETRY_ON_FAIL = 1        # Wie oft ein Chunk ohne Fortschritt erneut versucht wird
_GLOBAL_TIMEOUT_SEC = 5   # Harte Obergrenze für gesamten Löschteil (Sek.)

def _marker_at_frame(track, frame_current):
    # Finde Marker exakt auf aktuellem Frame, sonst None
    for m in track.markers:
        if m.frame == frame_current:
            return m
    return None

def run(context, values: dict, new_tracks=None, old_tracks=None, clip=None):
    """Bereinigt neu angelegte Marker, die zu nahe an bestehenden liegen.

    Algorithmus gemäß Vorgabe:
      Für jeden neuen Marker (NM) vergleiche mit allen alten Markern (AMA):
        - Koordinaten (normalized) * Auflösung -> Pixelpositionen
        - disH = |x_old - x_new|, disV = |y_old - y_new|
        - Wenn disH < md -> neuer Marker wird gelöscht
          Sonst wenn disV < md -> neuer Marker wird gelöscht
          Sonst bleibt er erhalten
    """
    if clip is None:
        clip = getattr(bpy.context, 'edit_movieclip', None)
    if not clip:
        print('cleaneup: kein Clip (Kontext ohne edit_movieclip)')
        return 0

    md = values.get('md')
    hz = values.get('hz')
    vc = values.get('vc')
    frame_current = context.scene.frame_current

    # Wenn externe Listen (aus compare.run) übergeben: nutzen, sonst selbst ermitteln
    prev_names = snapshot.get_previous_for_clip(clip)
    current_tracks = list(clip.tracking.tracks)
    if new_tracks is None or old_tracks is None:
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
                removed_now = bulk_delete.delete_tracks(chunk, clip=clip)
                removed += removed_now
                # Re-Check Clip stabil (kein erneuter Direktzugriff auf context wenn UI gewechselt)
                try:
                    current_clip = clip if clip and clip == bpy.context.edit_movieclip else clip
                except Exception:
                    current_clip = clip
                remaining_obj = []
                if current_clip:
                    try:
                        live_names = {t.name for t in current_clip.tracking.tracks}
                        for t in chunk:
                            # Wenn Name noch unverändert da und nicht logical markiert -> erneut versuchen
                            if t.name in live_names and not t.name.startswith('DELETED_'):
                                remaining_obj.append(t)
                    except Exception:
                        pass
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
    # Rückgabe: Anzahl der (nach Cleanup) gültigen neuen Marker
    try:
        surviving_new = [t for t in clip.tracking.tracks if t.name not in prev_names and not t.name.startswith('DELETED_')]
        return len(surviving_new)
    except Exception:
        return 0