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
    ops_tried = []
    # Mögliche Operator-Namen (Plural falls neue API?)
    operator_candidates = []
    try:
        operator_candidates.append(bpy.ops.clip.delete_track)
    except Exception:
        pass
    # Versuch plural
    try:
        operator_candidates.append(getattr(bpy.ops.clip, 'delete_tracks'))
    except Exception:
        pass
    # Tracking Namespace (Spekulation für API Änderung)
    try:
        operator_candidates.append(getattr(bpy.ops.clip.tracking, 'delete_track'))
    except Exception:
        pass
    try:
        operator_candidates.append(getattr(bpy.ops.clip.tracking, 'delete_tracks'))
    except Exception:
        pass

    for ctx in _iter_clip_context_variants(target_clip):
        # Sicherstellen Track selektiert + aktiv im aktuellen Real-Kontext
        try:
            for t in target_clip.tracking.tracks:
                t.select = False
            track.select = True
            target_clip.tracking.tracks.active = track
        except Exception:
            pass
        for op in operator_candidates:
            if op is None:
                continue
            op_name = getattr(op, '__name__', str(op))
            try:
                res = op(ctx)
                _log(f'Operator Versuch {op_name} mit Kontext {list(ctx.keys())} -> {res}')
                ops_tried.append((op_name, True, list(ctx.keys())))
                # Erfolg prüfen: Track verschwunden?
                remaining_names = [t.name for t in target_clip.tracking.tracks]
                if track.name not in remaining_names and not any(n.endswith(track.name) for n in remaining_names):
                    return True, ops_tried
            except Exception as e:
                ops_tried.append((op_name, False, f'{list(ctx.keys())} ERR={e}'))
                _log(f'Operator Fehlversuch {op_name} Kontext={list(ctx.keys())}: {e}')
    return False, ops_tried

def _try_temp_override_delete(track, target_clip):
    """Versucht Löschung über neue Context Override API (Blender 3.2+)."""
    wm = bpy.context.window_manager
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
                    # Auswahl setzen innerhalb Override
                    with bpy.context.temp_override(window=window, area=area, region=region, scene=bpy.context.scene, space_data=space):
                        for t in target_clip.tracking.tracks:
                            try: t.select = False
                            except Exception: pass
                        try:
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
                                    return True
                        except Exception as e:
                            _log(f'temp_override Fehler: {e}')
                except Exception as e:
                    _log(f'Override Setup Fehler: {e}')
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
        before_names = [t.name for t in clip.tracking.tracks]
        _log(f'Vor Löschung einzelner Track={name_before} Tracks={before_names}')
        success, attempts = _try_operator_delete_with_variants(target, clip)
        if success:
            total_removed += 1
            _log(f'Physisch entfernt (Operator Varianten): {name_before}')
            continue
        _log(f'Alle Operator-Varianten gescheitert für {name_before}. Attempts={attempts}')
        # Neuer Versuch über temp_override
        if _try_temp_override_delete(target, clip):
            total_removed += 1
            _log(f'Physisch entfernt (temp_override): {name_before}')
            continue
        # Direkter Remove Versuch falls vorhanden
        try:
            if hasattr(clip.tracking.tracks, 'remove'):
                clip.tracking.tracks.remove(target)
                total_removed += 1
                _log(f'Direkt entfernt via Collection.remove (nach Varianten): {name_before}')
                continue
            else:
                _log('Collection.remove nicht verfügbar – logical rename')
        except Exception as e2:
            _log(f'Direkter remove Fehler {name_before}: {e2}')
        # Logical rename Fallback
        if not name_before.startswith('DELETED_'):
            try:
                target.name = f'DELETED_{name_before}'
                _log(f'Logical umbenannt: {target.name}')
            except Exception:
                pass
    _log(f'Gesamt physisch entfernt: {total_removed} (logical markierte bleiben erhalten)')
    return total_removed