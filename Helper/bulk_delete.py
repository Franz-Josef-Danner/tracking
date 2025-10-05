import bpy

def _log(msg):
    print(f'[bulk_delete] {msg}')

def _find_clip_editor_context(target_clip):
    ctx_copy = None
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            space = area.spaces.active
            if getattr(space, 'clip', None) != target_clip:
                continue
            for region in area.regions:
                if region.type == 'WINDOW':
                    ctx_copy = bpy.context.copy()
                    ctx_copy['window'] = window
                    ctx_copy['area'] = area
                    ctx_copy['region'] = region
                    ctx_copy['space_data'] = space
                    # scene schon vorhanden
                    return ctx_copy
    return None

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
        _log('Kein gültiger CLIP_EDITOR Kontext gefunden – Abbruch')
        return 0

    # Selektion vorbereiten
    for t in clip.tracking.tracks:
        try:
            t.select = False
        except Exception:
            pass
    for t in to_delete:
        try:
            t.select = True
        except Exception:
            pass

    before = [t.name for t in clip.tracking.tracks]
    _log(f'Vorher Tracks: {before}')
    try:
        res = bpy.ops.clip.delete_track(ctx)
        _log(f'Operator delete_track Ergebnis: {res}')
    except Exception as e:
        _log(f'Operator Fehler: {e}')
        return 0
    after = [t.name for t in clip.tracking.tracks]
    _log(f'Nachher Tracks: {after}')
    removed = len(before) - len(after)
    _log(f'Entfernt (Differenz): {removed}')
    return removed