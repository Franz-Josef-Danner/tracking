import bpy

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

def delete_tracks(tracks):
    """Versucht mehrere Tracks mittels Operator in einem Durchgang zu löschen.

    tracks: Liste von MovieTrackingTrack Objekten
    """
    if not tracks:
        _log('Keine Tracks übergeben')
        return 0
    clip = bpy.context.edit_movieclip
    if not clip:
        _log('Kein aktiver Clip')
        return 0

    # Auflösen auf aktuelle Track-Objekte anhand des Namens (Veränderungen berücksichtigen)
    name_map = {t.name: t for t in clip.tracking.tracks}
    to_delete = []
    for t in tracks:
        nm = getattr(t, 'name', None)
        if nm in name_map:
            to_delete.append(name_map[nm])
    if not to_delete:
        _log('Keine übereinstimmenden Track-Namen')
        return 0

    # Versuch: jeden Track einzeln löschen (robuster als Multi-Select)
    total_removed = 0
    for target in to_delete:
        name_before = target.name
        ctx = _find_clip_editor_context(clip)
        if not ctx:
            _log(f'Kein Kontext für {name_before} – markiere nur (logical delete)')
            try:
                target.name = f'DELETED_UNREM_{name_before}'
            except Exception:
                pass
            continue
        # Alle deselektieren
        for t in clip.tracking.tracks:
            try:
                t.select = False
            except Exception:
                pass
        # Ziel selektieren + aktiv setzen
        try:
            target.select = True
            clip.tracking.tracks.active = target
        except Exception as e:
            _log(f'Set active/select fehlgeschlagen {name_before}: {e}')
        before_names = [t.name for t in clip.tracking.tracks]
        _log(f'Vor Löschung einzelner Track={name_before} Tracks={before_names}')
        try:
            res = bpy.ops.clip.delete_track(ctx)
            _log(f'Operator Einzel-Löschung {name_before} Ergebnis: {res}')
        except Exception as e:
            _log(f'Operator Fehler bei {name_before}: {e} – versuche direkten remove()')
            # Direkter Remove (falls API unterstützt)
            try:
                # Prüfen ob Collection remove unterstützt
                if hasattr(clip.tracking.tracks, 'remove'):
                    clip.tracking.tracks.remove(target)
                    _log(f'Direkt entfernt via Collection.remove: {name_before}')
                    total_removed += 1
                    continue
                else:
                    _log('Collection.remove nicht verfügbar – logical rename')
            except Exception as e2:
                _log(f'Direkter remove Fehler {name_before}: {e2}')
            # Logical Delete (Rename) als Fallback
            try:
                if not name_before.startswith('DELETED_'):
                    target.name = f'DELETED_{name_before}'
                    _log(f'Logical umbenannt: {target.name}')
            except Exception:
                pass
            continue
        # Erfolg prüfen: existiert Name noch?
        after_names = [t.name for t in clip.tracking.tracks]
        if name_before not in after_names:
            total_removed += 1
            _log(f'Bestätigt entfernt: {name_before}')
        else:
            _log(f'Noch vorhanden nach Operator: {name_before} – versuche rename logical')
            try:
                tgt = next((t for t in clip.tracking.tracks if t.name == name_before), None)
                if tgt and not tgt.name.startswith('DELETED_'):
                    tgt.name = f'DELETED_{name_before}'
                    _log(f'Logical rename fallback: {tgt.name}')
            except Exception:
                pass
    _log(f'Gesamt physisch entfernt: {total_removed} (logical markierte bleiben erhalten)')
    return total_removed