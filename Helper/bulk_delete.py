import bpy
import time

# Schlanke Konfiguration – nur was der aktuelle Löschpfad wirklich nutzt
SAFE_TOTAL_TIMEOUT = 4.0       # Max Zeit für einen gesamten delete_tracks Aufruf (Sek.)
SAFE_POST_REMOVE_SLEEP = 0.0   # Optionaler Sleep nach erfolgreichem Entfernen (0 = aus)

# Cache: hat temp_override je funktioniert? (True/False/None = noch nicht versucht)
_TEMP_OVERRIDE_CAPABLE = None

def _log(msg):
    print(f'[bulk_delete] {msg}')

def _try_temp_override_delete(track, target_clip):
    """Versucht Löschung über neue Context Override API (Blender 3.2+).

    Nutzt globales Cache-Flag für Capability.
    """
    global _TEMP_OVERRIDE_CAPABLE
    # Wenn bereits bekannt, dass es nicht geht: sofort abbrechen
    if _TEMP_OVERRIDE_CAPABLE is False:
        return False
    wm = bpy.context.window_manager
    start = time.perf_counter()
    # Nur erster passende CLIP_EDITOR wird verwendet (reduziert Mehrfach-Ausführungen / Instabilität)
    try:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type != 'CLIP_EDITOR':
                    continue
                space = area.spaces.active
                if getattr(space, 'clip', None) != target_clip:
                    continue
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if not region:
                    continue
                with bpy.context.temp_override(window=window, area=area, region=region, scene=bpy.context.scene, space_data=space):
                    try:
                        for t in target_clip.tracking.tracks:
                            t.select = False
                        track.select = True
                        target_clip.tracking.tracks.active = track
                    except Exception:
                        pass
                    try:
                        res = bpy.ops.clip.delete_track()
                        _log(f'temp_override Versuch delete_track -> {res}')
                        if res == {'FINISHED'}:
                            _TEMP_OVERRIDE_CAPABLE = True
                            dur = (time.perf_counter() - start) * 1000
                            _log(f'temp_override Rückkehr (nicht verifiziert) nach {dur:.1f}ms')
                            return True  # Erfolg (Verifikation erfolgt später durch Namens-Check)
                    except Exception as e:
                        _log(f'temp_override Fehler: {e}')
                # Nach erstem passenden Bereich abbrechen
                break
            if _TEMP_OVERRIDE_CAPABLE:
                break
    except Exception as outer_e:
        _log(f'temp_override global Fehler: {outer_e}')
    if _TEMP_OVERRIDE_CAPABLE is None:
        _TEMP_OVERRIDE_CAPABLE = False
    return False

def _track_exists(clip, name):
    try:
        for t in clip.tracking.tracks:
            if t.name == name:
                return True
    except Exception:
        pass
    return False

def delete_tracks(tracks, clip=None):
    """ Löscht übergebene Tracks robust (temp_override -> remove -> logical rename).

    tracks: iterable von Objekten mit .name
    clip: Optional MovieClip (sonst aus Kontext)
    Rückgabe: Anzahl physisch gelöschter Tracks
    """
    if not tracks:
        _log('Keine Tracks übergeben')
        return 0
    # Clip bevorzugt aus Parameter (stabilerer Kontext), sonst versuchen aus aktueller Context
    if clip is None:
        try:
            clip = getattr(bpy.context, 'edit_movieclip', None)
        except Exception:
            clip = None
    if not clip:
        _log('Kein Clip (Kontext hat kein edit_movieclip) – Abbruch ohne Fehler')
        return 0

    # Namen auflösen (frische Referenzen)
    # Eingaben in Namensliste normalisieren, um Dangling-Access zu vermeiden
    input_names = []
    for t in tracks:
        try:
            n = getattr(t, 'name', None)
            if n:
                input_names.append(n)
        except Exception:
            pass
    # Doppelte entfernen bei Mehrfachmarkierung
    seen = set()
    norm_names = []
    for n in input_names:
        if n not in seen:
            seen.add(n)
            norm_names.append(n)
    # Jetzt existierende Tracks filtern
    current_map = {t.name: t for t in clip.tracking.tracks}
    to_delete_names = [n for n in norm_names if n in current_map]
    if not to_delete_names:
        _log('Keine übereinstimmenden Track-Namen')
        return 0

    total_removed = 0
    start_total = time.perf_counter()
    for idx, name_before in enumerate(to_delete_names, 1):
        if (time.perf_counter() - start_total) > SAFE_TOTAL_TIMEOUT:
            _log('Abbruch: SAFE_TOTAL_TIMEOUT erreicht')
            break
        # Re-Resolve Track Objekt (kann sich ändern / gelöscht worden sein)
        current_obj = None
        try:
            current_obj = next((t for t in clip.tracking.tracks if t.name == name_before), None)
        except Exception:
            current_obj = None
        if current_obj is None:
            _log(f'Skip {name_before}: bereits entfernt')
            continue
        _log(f'[{idx}/{len(to_delete_names)}] Lösche Track {name_before}')
        start_track = time.perf_counter()
        # Nur ein Versuchspfad (temp_override) – danach direkter remove / logical rename
        methods = ['temp']

        removed = False
        for m in methods:
            # Objekt vor jedem Versuch neu auflösen (kann verschwunden sein)
            try:
                target = next((t for t in clip.tracking.tracks if t.name == name_before), None)
            except Exception:
                target = None
            if target is None:
                removed = True  # Schon weg
                break
            if m == 'temp':
                if _try_temp_override_delete(target, clip):
                    # Nachlauf-Prüfung ob Name noch existiert
                    if not _track_exists(clip, name_before):
                        removed = True
                        _log(f'Removed via temp_override: {name_before}')
                        break
                    else:
                        _log(f'temp_override meldete FINISHED, Track {name_before} existiert jedoch noch')

        if not removed:
            # Direkter remove Versuch falls vorhanden
            try:
                target = next((t for t in clip.tracking.tracks if t.name == name_before), None)
                if target and hasattr(clip.tracking.tracks, 'remove'):
                    clip.tracking.tracks.remove(target)
                    if not _track_exists(clip, name_before):
                        removed = True
                        _log(f'Removed via collection.remove: {name_before}')
            except Exception as e2:
                _log(f'collection.remove Fehler {name_before}: {e2}')

        if not removed:
            # Logical Rename Fallback (erneut auflösen um Zombie Referenzen zu vermeiden)
            try:
                target = next((t for t in clip.tracking.tracks if t.name == name_before), None)
                if target and not name_before.startswith('DELETED_'):
                    target.name = f'DELETED_{name_before}'
                    _log(f'Logical rename -> {target.name}')
                elif target is None:
                    removed = True  # bereits verschwunden
            except Exception:
                _log('Logical rename fehlgeschlagen (ignoriert)')
        else:
            total_removed += 1

        if removed and SAFE_POST_REMOVE_SLEEP > 0:
            try:
                time.sleep(SAFE_POST_REMOVE_SLEEP)
            except Exception:
                pass
        dur_ms = (time.perf_counter() - start_track) * 1000
        _log(f'Fertig Track {name_before} ({dur_ms:.1f}ms) removed={removed}')

        # UI entlasten: leichter Redraw Impuls
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

    _log(f'Gesamt physisch entfernt: {total_removed} / {len(to_delete_names)} (Rest logical)')
    return total_removed