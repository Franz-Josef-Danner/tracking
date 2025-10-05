import bpy
import time

# ===== Safe Mode Optionen =====
# Wenn True: Nur temp_override (oder direct remove) – keine Operator-Varianten
SAFE_MODE = True
# Max Gesamtzeit pro delete_tracks Aufruf (Sekunden)
SAFE_TOTAL_TIMEOUT = 4.0
# Minimale Pause (Sekunden) nach physischem Entfernen zur internen Aktualisierung
SAFE_POST_REMOVE_SLEEP = 0.0

# Globale Caches / Flags zur Laufzeit zur Stabilitäts-/Performance-Steigerung
# Sobald klar ist, dass Operator-Löschung nicht funktioniert, sparen wir uns weitere Versuche.
_OPERATOR_DELETE_UNSUPPORTED = False
# Merkt sich, ob temp_override Löschung mind. einmal funktioniert hat (True) oder sicher fehlgeschlagen ist (False)
_TEMP_OVERRIDE_CAPABLE = None  # None = noch nicht getestet

# Konfigurierbare Limits
MAX_OPERATOR_ATTEMPTS_PER_TRACK = 6  # Hartes Limit, danach Abbruch
MAX_RECORDED_ATTEMPTS = 12           # Wie viele Detail-Einträge wir pro Track speichern
OPERATOR_FIRST_DEFAULT = False       # Falls True zuerst Operator statt temp_override
ABORT_ON_IDENTICAL_ERROR_SERIES = 3  # Nach X identischen Fehlern gleicher Signatur abbrechen

def _log(msg):
    print(f'[bulk_delete] {msg}')

def _debug_list_clip_editors(target_clip):
    try:
        wm = bpy.context.window_manager
        for window in wm.windows:
            _log(f'Check Window id={window.as_pointer()} screen={getattr(window.screen,"name",None)}')
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    space = area.spaces.active
                    clip_name = getattr(getattr(space, 'clip', None), 'name', None)
                    _log(f'  Area(CLIP_EDITOR) clip={clip_name} match={clip_name == getattr(target_clip,"name",None)}')
    except Exception as e:
        _log(f'Debug Listing Error: {e}')

def _find_clip_editor_context(target_clip):
    ctx_copy = None
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            space = area.spaces.active
            # Sicherstellen, dass der gewünschte Clip wirklich gesetzt ist
            try:
                if getattr(space, 'clip', None) != target_clip:
                    continue
            except Exception:
                continue
            for region in area.regions:
                if region.type == 'WINDOW':
                    ctx_copy = bpy.context.copy()
                    ctx_copy['window'] = window
                    ctx_copy['screen'] = screen
                    ctx_copy['area'] = area
                    ctx_copy['region'] = region
                    ctx_copy['space_data'] = space
                    ctx_copy['edit_movieclip'] = target_clip
                    # scene bereits vorhanden, aber sicherheitshalber
                    ctx_copy['scene'] = bpy.context.scene
                    return ctx_copy
    if ctx_copy is None:
        _log('Kein passender CLIP_EDITOR Kontext gefunden')
        _debug_list_clip_editors(target_clip)
    return ctx_copy

def _iter_clip_context_variants(target_clip):
    """Erzeugt verschiedene Minimal-Kontexte für Operator-Aufrufe.

    Einige Blender-Versionen akzeptieren nur sehr schlanke Overrides.
    """
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            space = area.spaces.active
            if getattr(space, 'clip', None) != target_clip:
                continue
            # Variante 1: Voll
            full = bpy.context.copy()
            for region in area.regions:
                if region.type == 'WINDOW':
                    full.update({'window': window, 'screen': screen, 'area': area, 'region': region, 'space_data': space, 'scene': bpy.context.scene})
                    yield full
                    # Variante 2: Minimal (nur area/region/space_data)
                    minimal = {'area': area, 'region': region, 'space_data': space}
                    yield minimal
                    # Variante 3: Minimal + scene
                    minimal_scene = {'area': area, 'region': region, 'space_data': space, 'scene': bpy.context.scene}
                    yield minimal_scene
                    # Variante 4: Ohne region (manchmal tolerant)
                    yield {'area': area, 'space_data': space}
                    break

def _try_operator_delete_with_variants(track, target_clip):
    """Versucht verschiedene Operator- / Kontext-Kombinationen.

    Mit Limits versehen, damit UI nicht blockiert.
    Nutzt globales Flag _OPERATOR_DELETE_UNSUPPORTED um erneute Massen-Versuche zu vermeiden.
    """
    global _OPERATOR_DELETE_UNSUPPORTED
    if SAFE_MODE:
        return False, [('SKIPPED', False, 'SAFE_MODE aktiv – Operator übersprungen')]
    if _OPERATOR_DELETE_UNSUPPORTED:
        return False, [('SKIPPED', False, 'Operator bereits als unsupported markiert')]

    ops_tried = []
    operator_candidates = []
    # Kandidaten sammeln (robust, stillschweigend fehlertolerant)
    for getter in (
        lambda: bpy.ops.clip.delete_track,
        lambda: getattr(bpy.ops.clip, 'delete_tracks'),
        lambda: getattr(bpy.ops.clip.tracking, 'delete_track'),
        lambda: getattr(bpy.ops.clip.tracking, 'delete_tracks'),
    ):
        try:
            c = getter()
            if c not in operator_candidates:
                operator_candidates.append(c)
        except Exception:
            pass

    attempt_count = 0
    last_error_sig = None
    identical_error_series = 0

    for ctx in _iter_clip_context_variants(target_clip):
        # Auswahl vorbereiten
        try:
            for t in target_clip.tracking.tracks:
                t.select = False
            track.select = True
            target_clip.tracking.tracks.active = track
        except Exception:
            pass
        for op in operator_candidates:
            if attempt_count >= MAX_OPERATOR_ATTEMPTS_PER_TRACK:
                _log('Abbruch weiterer Operator-Versuche (Limit erreicht)')
                if not ops_tried:
                    ops_tried.append(('ABORT_LIMIT', False, 'Keine Versuche protokolliert'))
                return False, ops_tried
            attempt_count += 1
            op_name = getattr(op, '__name__', str(op))
            keys_list = list(ctx.keys())
            try:
                res = op(ctx)
                ops_tried.append((op_name, True, keys_list))
                _log(f'Operator Versuch {op_name} ({attempt_count}) -> {res}')
                remaining = [t.name for t in target_clip.tracking.tracks]
                if track.name not in remaining:
                    return True, ops_tried
            except Exception as e:
                # Fehler-Signatur für Kompressions- / Abbruchlogik
                err_sig = str(type(e)) + ':' + str(e)
                if err_sig == last_error_sig:
                    identical_error_series += 1
                else:
                    identical_error_series = 1
                    last_error_sig = err_sig
                # Komprimiertes Logging: nur jede 2. Wiederholung ausführlich
                if identical_error_series <= 2:
                    _log(f'Operator Fehlversuch {op_name} ({attempt_count}) Kontext={keys_list}: {e}')
                elif identical_error_series == ABORT_ON_IDENTICAL_ERROR_SERIES:
                    _log(f'Immer gleicher Fehler ({err_sig}) – breche Operator-Schleife früh ab')
                    _OPERATOR_DELETE_UNSUPPORTED = True
                    ops_tried.append((op_name, False, f'{keys_list} ERR={e} EARLY_ABORT'))
                    return False, ops_tried
                ops_tried.append((op_name, False, f'{keys_list} ERR={e}'))
            # Versuche Anzahl aufgezeichnete Entries zu begrenzen
            if len(ops_tried) > MAX_RECORDED_ATTEMPTS:
                ops_tried.append(('TRUNCATED', False, f'max {MAX_RECORDED_ATTEMPTS} reached'))
                return False, ops_tried
    # Wenn wir hierher gelangen und nichts funktioniert hat: global auf unsupported setzen
    _OPERATOR_DELETE_UNSUPPORTED = True
    return False, ops_tried

def _try_temp_override_delete(track, target_clip):
    """Versucht Löschung über neue Context Override API (Blender 3.2+).

    Nutzt globales Cache-Flag für Capability.
    """
    global _TEMP_OVERRIDE_CAPABLE
    # Wenn bereits bekannt, dass es nicht geht: sofort abbrechen
    if SAFE_MODE:
        # In Safe Mode immer versuchen; Capability Cache weiterhin nutzen
        if _TEMP_OVERRIDE_CAPABLE is False:
            return False
    else:
        if _TEMP_OVERRIDE_CAPABLE is False:
            return False
    wm = bpy.context.window_manager
    start = time.perf_counter()
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            space = area.spaces.active
            if getattr(space, 'clip', None) != target_clip:
                continue
            for region in area.regions:
                if region.type != 'WINDOW':
                    continue
                try:
                    with bpy.context.temp_override(window=window, area=area, region=region, scene=bpy.context.scene, space_data=space):
                        # Auswahl setzen
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
                                remaining = [t.name for t in target_clip.tracking.tracks]
                                if track.name not in remaining:
                                    _TEMP_OVERRIDE_CAPABLE = True
                                    dur = (time.perf_counter() - start) * 1000
                                    _log(f'temp_override Erfolg nach {dur:.1f}ms')
                                    return True
                        except Exception as e:
                            _log(f'temp_override Fehler: {e}')
                except Exception as e:
                    _log(f'Override Setup Fehler: {e}')
    # Kein Erfolg
    if _TEMP_OVERRIDE_CAPABLE is None:
        _TEMP_OVERRIDE_CAPABLE = False
    return False

def purge_logically_deleted(target_clip=None):
    """Entfernt alle Tracks deren Name mit DELETED_ beginnt sofern API es erlaubt.

    Falls physisches Entfernen nicht geht, werden sie lediglich gezählt.
    """
    if target_clip is None:
        target_clip = bpy.context.edit_movieclip
    if not target_clip:
        _log('purge: kein Clip')
        return {'removed': 0, 'remaining_deleted': 0}
    deleted_tracks = [t for t in target_clip.tracking.tracks if t.name.startswith('DELETED_')]
    removed = 0
    if hasattr(target_clip.tracking.tracks, 'remove'):
        for t in list(deleted_tracks):
            try:
                target_clip.tracking.tracks.remove(t)
                removed += 1
            except Exception as e:
                _log(f'purge remove Fehler {t.name}: {e}')
    else:
        _log('purge: Collection.remove nicht verfügbar – nur zählen')
    remaining_deleted = len([t for t in target_clip.tracking.tracks if t.name.startswith('DELETED_')])
    _log(f'purge: entfernt={removed} verbleibend_markiert={remaining_deleted}')
    return {'removed': removed, 'remaining_deleted': remaining_deleted}

def delete_tracks(tracks, strategy='auto'):
    """ Löscht mehrere Tracking-Tracks stabil mit mehrstufigem Fallback.

    Parameter:
      tracks   : Iterable von MovieTrackingTrack (oder Objekten mit .name)
      strategy : 'auto' | 'temp_first' | 'operator_first'
                 auto          -> nutzt Heuristik (temp_override bevorzugen sobald erfolgreich)
                 temp_first    -> versucht temp_override zuerst pro Track
                 operator_first-> zwingt Operator zuerst (innerhalb Limits)
    Rückgabe: Anzahl physisch entfernter Tracks
    """
    if not tracks:
        _log('Keine Tracks übergeben')
        return 0
    clip = bpy.context.edit_movieclip
    if not clip:
        _log('Kein aktiver Clip')
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
    use_operator_first = (not SAFE_MODE) and ((strategy == 'operator_first') or (strategy == 'auto' and not _TEMP_OVERRIDE_CAPABLE and OPERATOR_FIRST_DEFAULT))
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

        # Reihenfolge bestimmen je nach Strategie / Safe Mode
        methods = []
        if SAFE_MODE:
            methods = ['temp']
        else:
            if strategy == 'temp_first' or (strategy == 'auto' and _TEMP_OVERRIDE_CAPABLE):
                methods = ['temp', 'operator']
            elif use_operator_first:
                methods = ['operator', 'temp']
            else:
                methods = ['temp', 'operator']

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
                    removed = True
                    _log(f'Removed via temp_override: {name_before}')
                    break
            elif m == 'operator':
                success, attempts = _try_operator_delete_with_variants(target, clip)
                if success:
                    removed = True
                    _log(f'Removed via Operator: {name_before}')
                    break
                else:
                    if attempts:
                        last = attempts[-1]
                        _log(f'Operator fehlgeschlagen (summary letzte={last})')

        if not removed:
            # Direkter remove Versuch falls Collection.remove existiert (neu auflösen)
            try:
                target = next((t for t in clip.tracking.tracks if t.name == name_before), None)
                if target and hasattr(clip.tracking.tracks, 'remove'):
                    clip.tracking.tracks.remove(target)
                    removed = True
                    _log(f'Removed via collection.remove: {name_before}')
            except Exception as e2:
                _log(f'collection.remove Fehler {name_before}: {e2}')

        if not removed:
            # Logical Rename Fallback
            if not name_before.startswith('DELETED_'):
                try:
                    target.name = f'DELETED_{name_before}'
                    _log(f'Logical rename -> {target.name}')
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

        # UI entlasten: leichter Redraw Impuls (sofern Operator existiert)
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

    _log(f'Gesamt physisch entfernt: {total_removed} / {len(to_delete_names)} (Rest logical)')
    return total_removed