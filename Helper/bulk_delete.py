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

    ctx = _find_clip_editor_context(clip)
    if not ctx:
        _log('Versuche Fallback ohne Operator (direktes Entfernen)')
        # Fallback direkt ohne Operator
        removed = 0
        existing = list(clip.tracking.tracks)
        name_set = {t.name for t in to_delete}
        for trk in existing:
            if trk.name in name_set:
                try:
                    clip.tracking.tracks.remove(trk)
                    removed += 1
                    _log(f'Fallback entfernt Track: {trk.name}')
                except Exception as e:
                    _log(f'Fallback Fehler Track {trk.name}: {e}')
        _log(f'Fallback Entfernt: {removed}')
        return removed

    # Selektion vorbereiten + aktiver Track setzen
    active_set = False
    for t in clip.tracking.tracks:
        try:
            t.select = False
        except Exception:
            pass
    for i, t in enumerate(to_delete):
        try:
            t.select = True
            if not active_set:
                clip.tracking.tracks.active = t
                active_set = True
        except Exception:
            pass

    before = [t.name for t in clip.tracking.tracks]
    _log(f'Vorher Tracks: {before}')
    _log('Selektiert für Löschung: ' + ', '.join([t.name for t in to_delete]))
    try:
        res = bpy.ops.clip.delete_track(ctx)
        _log(f'Operator delete_track Ergebnis: {res}')
    except Exception as e:
        _log(f'Operator Fehler: {e} – Fallback Entfernen einzelner Tracks')
        removed = 0
        existing = list(clip.tracking.tracks)
        name_set = {t.name for t in to_delete}
        for trk in existing:
            if trk.name in name_set:
                try:
                    clip.tracking.tracks.remove(trk)
                    removed += 1
                    _log(f'Fallback entfernt Track: {trk.name}')
                except Exception as e2:
                    _log(f'Fallback Fehler Track {trk.name}: {e2}')
        _log(f'Fallback Entfernt: {removed}')
        return removed
    after = [t.name for t in clip.tracking.tracks]
    _log(f'Nachher Tracks: {after}')
    removed = len(before) - len(after)
    _log(f'Entfernt (Differenz): {removed}')
    return removed