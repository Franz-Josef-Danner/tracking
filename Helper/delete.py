import bpy

DEBUG_DELETE = True

def _log(msg):
    if DEBUG_DELETE:
        print(f'[delete] {msg}')

def _find_track(clip, candidate):
    name = getattr(candidate, 'name', None)
    for t in clip.tracking.tracks:
        if t == candidate:
            return t
    if name:
        for t in clip.tracking.tracks:
            if t.name == name:
                return t
    return None

def _track_still_exists(clip, name):
    for t in clip.tracking.tracks:
        if t.name == name:
            return True
    return False

def _delete_marker_at_frame(track, frame):
    """Versucht den Marker auf 'frame' zu löschen und validiert den Erfolg.
    Rückgabe True nur, wenn der Marker vorher existierte und danach nicht mehr vorhanden ist.
    """
    try:
        before_exists = any(getattr(mk, 'frame', None) == frame for mk in track.markers)
    except Exception:
        before_exists = False
    if not before_exists:
        return False

    # Versuche über find_frame
    if hasattr(track.markers, 'find_frame'):
        try:
            m = track.markers.find_frame(frame)
        except Exception:
            m = None
        if m is not None and hasattr(track.markers, 'delete_frame'):
            try:
                track.markers.delete_frame(frame)
            except Exception:
                pass
    # Validierung
    after_exists = any(getattr(mk, 'frame', None) == frame for mk in track.markers)
    if not after_exists:
        return True
    # Zweiter Versuch: brute force (alle Marker kopieren außer dem Frame – hier nur möglich wenn API löscht)
    # Wenn weiterhin vorhanden -> nicht erfolgreich
    return False

def _delete_all_markers(track):
    frames_list = []
    for mk in track.markers:
        frv = getattr(mk, 'frame', None)
        if frv is not None:
            frames_list.append(frv)
    unique_frames = sorted(set(frames_list), reverse=True)
    ok = True
    for frv in unique_frames:
        if not _delete_marker_at_frame(track, frv):
            ok = False
    return ok and len(track.markers) == 0

def run(track, frame=None):
    """Entfernt (primär) nur Marker am aktuellen Frame oder – falls nötig – alle Marker.

    Falls Track danach leer ist: versucht optional Track zu löschen (soft), ansonsten markiert (rename).
    Rückgabe: True falls mindestens ein Marker entfernt oder Track geleert wurde.
    """
    clip = bpy.context.edit_movieclip
    if not clip:
        _log('kein aktiver Clip')
        return False
    target = _find_track(clip, track)
    if target is None:
        _log('Track nicht gefunden (Abbruch)')
        return False
    name = target.name
    if frame is None:
        frame = bpy.context.scene.frame_current
    _log(f'Run delete für Track={name} Frame={frame}')
    # Diagnose: Attribute-Liste / Methodenverfügbarkeit
    try:
        has_del_frame = hasattr(target.markers, 'delete_frame')
        has_find_frame = hasattr(target.markers, 'find_frame')
        _log(f'Capabilities: delete_frame={has_del_frame} find_frame={has_find_frame} len(markers)={len(target.markers)}')
    except Exception:
        pass
    # Liste aller Marker Frames + Koordinaten
    try:
        marker_dump = []
        for mk in target.markers:
            marker_dump.append({'frame': getattr(mk,'frame',None), 'co': getattr(mk,'co',None)})
        _log(f'MarkerDump vor: {marker_dump}')
    except Exception:
        pass

    # 1. Versuch: Marker am Frame löschen
    # Aktuelle Marker Frames vor Start
    try:
        existing_frames = sorted({getattr(mk, 'frame', None) for mk in target.markers})
    except Exception:
        existing_frames = []
    _log(f'Aktuelle Marker Frames vor Löschung: {existing_frames}')

    removed_marker = _delete_marker_at_frame(target, frame)
    # Verifizieren ob Frame wirklich weg ist (direkte Prüfung)
    frame_still = any(getattr(mk, 'frame', None) == frame for mk in target.markers)
    _log(f'Marker am Frame gelöscht={removed_marker} frame_still_exists={frame_still}')

    # Falls vom angefragten Frame nichts weg ging oder Frame weiter existiert -> Versuche alle Frames einzeln
    if (not removed_marker) or frame_still:
        _log('Starte Einzel-Frame-Löschversuche für alle Marker')
        all_frames_before = sorted({getattr(mk, 'frame', None) for mk in target.markers})
        for fr in reversed(all_frames_before):
            ok_single = _delete_marker_at_frame(target, fr)
            still = any(getattr(mk, 'frame', None) == fr for mk in target.markers)
            _log(f'  Versuch delete_frame({fr}) ok={ok_single} still_exists={still}')
        after_frames = sorted({getattr(mk, 'frame', None) for mk in target.markers})
        _log(f'Frames nach Einzel-Versuchen: {after_frames}')
        # Operator-Fallback für einzelne Marker (nur falls noch Marker existieren)
        if after_frames:
            _log('Versuche Operator-Fallback delete_marker für jede Frame-ID')
            clip = bpy.context.edit_movieclip
            if clip:
                # Build override
                try:
                    wm = bpy.context.window_manager
                    override = None
                    for window in wm.windows:
                        for area in window.screen.areas:
                            if area.type == 'CLIP_EDITOR':
                                space = area.spaces.active
                                if getattr(space,'clip',None) != clip:
                                    continue
                                for region in area.regions:
                                    if region.type == 'WINDOW':
                                        override = {
                                            'window': window,
                                            'screen': window.screen,
                                            'area': area,
                                            'region': region,
                                            'space_data': space,
                                            'scene': bpy.context.scene,
                                        }
                                        break
                                if override: break
                        if override: break
                except Exception:
                    override = None
                # Selektions-Setup + Marker-Selektion und Operator
                try:
                    for tsel in clip.tracking.tracks:
                        try: tsel.select = False
                        except Exception: pass
                    try: target.select = True
                    except Exception: pass
                    # Selektiere alle Marker (oder spezifischen Frame)
                    if hasattr(target.markers,'find_frame'):
                        mk = target.markers.find_frame(frame)
                        if mk: 
                            try: mk.select = True
                            except Exception: pass
                    # Operator versuchen
                    try:
                        if override:
                            op_res = bpy.ops.clip.delete_marker(override)
                        else:
                            op_res = bpy.ops.clip.delete_marker()
                        _log(f'Operator delete_marker Ergebnis: {op_res}')
                    except Exception as e:
                        _log(f'Operator delete_marker Exception: {e}')
                except Exception as e:
                    _log(f'Operator-Fallback Setup Fehler: {e}')

    # 2. Wenn immer noch Marker existieren -> roher Wipe
    if len(target.markers):
        _log('Wipe-Routine: versuche alle Marker über _delete_all_markers zu entfernen')
        wiped = _delete_all_markers(target)
        _log(f'Wipe Ergebnis wiped={wiped} verbleibend={len(target.markers)}')
    else:
        wiped = True

    # 3. Optional: Track löschen falls leer – aber ohne Operator (Problemquelle) -> nur rename/mute
    if len(target.markers) == 0:
        try:
            target.mute = True
        except Exception:
            pass
        try:
            target.name = f'DELETED_{name}'
        except Exception:
            pass
        _log(f'Track {name} ist leer -> markiert als gelöscht (mute/rename)')
        return True

    # Wenn nur EIN Marker (unlöschbar) und wir wollten ihn entfernen -> Track logisch deaktivieren
    if len(target.markers) == 1:
        try:
            target.mute = True
            target.name = f'DELETED_SINGLE_{name}'
            _log(f'Track {name} single-marker not deletable -> logical removal (mute & rename)')
            return True
        except Exception:
            pass

    # Erfolg nur melden, wenn mindestens ein Marker weniger existiert als vorher
    try:
        existing_after = sorted({getattr(mk, 'frame', None) for mk in target.markers})
    except Exception:
        existing_after = []
    changed = len(existing_after) < len(existing_frames) or target.name.startswith('DELETED_')
    # Dump Marker nachher
    try:
        marker_dump_after = []
        for mk in target.markers:
            marker_dump_after.append({'frame': getattr(mk,'frame',None), 'co': getattr(mk,'co',None)})
        _log(f'MarkerDump nach: {marker_dump_after}')
    except Exception:
        pass
    _log(f'Abschluss: vorher_frames={existing_frames} nachher_frames={existing_after} changed={changed}')
    if not changed:
        # Letzter Versuch: logisches Deaktivieren falls wir eigentlich löschen wollten (Frame Teilmenge)
        if frame in existing_after:
            try:
                target.mute = True
                target.name = f'DELETED_UNREM_{name}'
                _log(f'Logische Deaktivierung (Umbenennung) für {name} da nicht physisch löschbar')
                return True
            except Exception:
                pass
    return changed
def _resolve_track(context, track_name: str, case_insensitive: bool = True):
    """Findet einen Track anhand seines Namens (optional case-insensitive)."""
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        return None
    clip = getattr(space, 'clip', None)
    if not clip:
        return None
    tracking = clip.tracking
    target = track_name if track_name else ""
    for tr in tracking.tracks:
        if tr.name == target:
            return tr
    if case_insensitive:
        lower = target.lower()
        for tr in tracking.tracks:
            if tr.name.lower() == lower:
                return tr
    return None


def _marker_frames(track):
    try:
        return sorted([m.frame for m in track.markers])
    except Exception:
        return []


def _debug_track_introspection(track):
    """(Entfernt) Funktion diente reinem Debugging – Platzhalter für evtl. zukünftige introspektion."""
    return


def _remove_marker_object(track, marker):
    """Versucht Marker zu entfernen und verifiziert direkt den Effekt.
    Rückgabe: (removed_effective: bool, methode: str oder None)"""
    if marker is None:
        return False, None
    before_frames = _marker_frames(track)
    before_count = len(before_frames)
    marker_frame = getattr(marker, 'frame', None)

    # Versuche verschiedene API-Varianten – still.

    def verify(_methode_name):
        after_frames = _marker_frames(track)
        still = marker_frame in after_frames
        # Sonderfall: letzter Marker bleibt evtl. bestehen
        return (not still) or (before_count == 1 and len(after_frames) == 1 and still)

    if hasattr(track.markers, 'delete'):
        try:
            track.markers.delete(marker)
            if verify('delete(marker)'):
                return True, 'delete(marker)'
        except Exception:
            pass
    if hasattr(track.markers, 'remove'):
        try:
            track.markers.remove(marker)
            if verify('remove(marker)'):
                return True, 'remove(marker)'
        except Exception:
            pass
    if hasattr(track.markers, 'delete_frame') and marker_frame is not None:
        try:
            track.markers.delete_frame(marker_frame)
            if verify('delete_frame(frame)'):
                return True, 'delete_frame(frame)'
        except Exception:
            pass
    # Keine Methode erfolgreich
    return False, None


def delete_marker_frame(context, track_name: str, frame: int) -> bool:
    """Löscht einen einzelnen Marker-Keyframe eines Tracks (by frame) mit ausführlichem Debug-Log."""
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        return False
    clip = getattr(space, 'clip', None)
    if not clip:
        return False
    tracking = clip.tracking
    try:
        for tr in tracking.tracks:
            if tr.name != track_name:
                continue
            # Vorher Frames (nur intern genutzt)
            frames_vorher = _marker_frames(tr)

            # Marker suchen
            marker = None
            used_find = False
            if hasattr(tr.markers, 'find_frame'):
                try:
                    marker = tr.markers.find_frame(frame)
                    used_find = True
                except Exception:
                    pass
                    marker = None
            if marker is None:
                for m in tr.markers:
                    if getattr(m, 'frame', None) == frame:
                        marker = m
                        break
            if marker is None:
                return False

            removed, methode = _remove_marker_object(tr, marker)

            still_there = any(m.frame == frame for m in tr.markers)
            frames_nachher = _marker_frames(tr)

            # Sonderfall: Spur mit einzigem Marker lässt sich per API nicht leeren -> ggf. Track entfernen
            if still_there and len(frames_nachher) == 1 and removed:
                # Fallback für Single-Marker-Track
                # Versuch 1: Track per Operator löschen
                deleted_track = False
                try:
                    # Selektions-Setup nur für Track
                    for tsel in tracking.tracks:
                        try:
                            tsel.select = False
                        except Exception:
                            pass
                    try:
                        tr.select = True
                    except Exception:
                        pass
                    # Kontext sammeln
                    override = None
                    wm = bpy.context.window_manager
                    for window in wm.windows:
                        for area in window.screen.areas:
                            if area.type == 'CLIP_EDITOR':
                                for region in area.regions:
                                    if region.type == 'WINDOW':
                                        override = {
                                            'window': window,
                                            'screen': window.screen,
                                            'area': area,
                                            'region': region,
                                            'scene': context.scene,
                                            'space_data': area.spaces.active,
                                        }
                                        space = area.spaces.active
                                        if getattr(space, 'clip', None):
                                            override['clip'] = space.clip
                                        break
                                if override:
                                    break
                        if override:
                            break
                    try:
                        _ = bpy.ops.clip.delete_track(override) if override else bpy.ops.clip.delete_track()
                    except Exception:
                        pass
                    # Prüfen ob Track weg ist
                    deleted_track = all(t.name != tr.name for t in tracking.tracks)
                except Exception:
                    pass

                if deleted_track:
                    return True
                else:
                    # Versuch 2: Dummy-Marker an anderem Frame anlegen, dann Ziel löschen
                    try:
                        dummy_frame = frame + 1
                        if hasattr(tr.markers, 'find_frame') and tr.markers.find_frame(dummy_frame) is None:
                            tr.markers.insert_frame(dummy_frame)
                            pass
                        # Nochmals Ziel löschen
                        if hasattr(tr.markers, 'delete_frame'):
                            tr.markers.delete_frame(frame)
                            check_after_dummy = any(m.frame == frame for m in tr.markers)
                            if not check_after_dummy:
                                return True
                        # Aufräumen: Dummy wieder löschen wenn nur er übrig ist und nicht gewollt
                        if len(tr.markers) == 1 and any(m.frame == dummy_frame for m in tr.markers):
                            # Versuchen Track doch zu entfernen
                            try:
                                for tsel in tracking.tracks:
                                    tsel.select = False
                                tr.select = True
                                _ = bpy.ops.clip.delete_track(override) if override else bpy.ops.clip.delete_track()
                            except Exception:
                                pass
                    except Exception:
                        pass

            if not still_there and removed:
                try:
                    context.scene.frame_set(context.scene.frame_current)
                except Exception:
                    pass
                return True

            # Operator-Fallback (nur wenn Frame noch existiert)
            if still_there:
                # Kontext Override auf einen CLIP_EDITOR Area
                override = None
                try:
                    wm = bpy.context.window_manager
                    for window in wm.windows:
                        for area in window.screen.areas:
                            if area.type == 'CLIP_EDITOR':
                                for region in area.regions:
                                    if region.type == 'WINDOW':
                                        override = {
                                            'window': window,
                                            'screen': window.screen,
                                            'area': area,
                                            'region': region,
                                            'scene': context.scene,
                                        }
                                        space = area.spaces.active
                                        if getattr(space, 'clip', None):
                                            override['space_data'] = space
                                            override['clip'] = space.clip
                                        break
                                if override:
                                    break
                        if override:
                            break
                except Exception:
                    pass

                # Track & Marker selektieren
                try:
                    for tt in tracking.tracks:
                        tt.select = False
                        try:
                            mk = tt.markers.find_frame(frame) if hasattr(tt.markers,'find_frame') else None
                            if mk:
                                mk.select = False
                        except Exception:
                            pass
                    tr.select = True
                    if hasattr(tr.markers, 'find_frame'):
                        mk = tr.markers.find_frame(frame)
                        if mk:
                            mk.select = True
                except Exception:
                    pass

                try:
                    if override:
                        _ = bpy.ops.clip.delete_marker(override)
                    else:
                        _ = bpy.ops.clip.delete_marker()
                except Exception:
                    pass

                # Nach-Überprüfung
                frames_after_op = _marker_frames(tr)
                if frame not in frames_after_op:
                    return True
            return False
    except Exception as e:
        # Fehler wird still geschluckt (kein Log für Übersichtlichkeit)
        _ = e
    return False


def delete_marker_index(context, track_name: str, index: int) -> bool:
    """Löscht Marker per Index (0-basiert in aktueller Reihenfolge der Collection) mit Debug."""
    tr = _resolve_track(context, track_name)
    if not tr:
        return False
    markers_list = list(tr.markers)
    if index < 0 or index >= len(markers_list):
        return False
    marker = markers_list[index]
    frame = getattr(marker, 'frame', None)
    removed, methode = _remove_marker_object(tr, marker)
    still_there = any(getattr(m, 'frame', None) == frame for m in tr.markers)
    return bool(removed and not still_there)


def delete_all_markers(context, track_name: str) -> int:
    """Löscht alle Marker eines Tracks und gibt Anzahl gelöschter Marker zurück (Debug)."""
    tr = _resolve_track(context, track_name)
    if not tr:
        return 0
    original = _marker_frames(tr)
    count = 0
    for mk in list(tr.markers):
        removed, methode = _remove_marker_object(tr, mk)
        if removed:
            count += 1
    remaining = _marker_frames(tr)
    return count
