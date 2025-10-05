import bpy

# Globale Debug-Flag (bei Bedarf auf False setzen um die Menge zu reduzieren)
DEBUG_DELETE = True

def _log(msg):
    if DEBUG_DELETE:
        print(f'[delete] {msg}')

def _build_override_for_clip(target_clip):
    """Versucht einen gültigen Override-Kontext für den Clip Editor zu erstellen."""
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
                    override = {
                        'window': window,
                        'screen': window.screen,
                        'area': area,
                        'region': region,
                        'space_data': space,
                        'scene': bpy.context.scene,
                        'clip': target_clip,
                    }
                    return override
    return None

def _manual_track_wipe(track):
    """Fallback: löscht alle Marker einzeln, versucht danach erneut Operator."""
    frames = []
    try:
        for m in track.markers:
            fr = getattr(m, 'frame', None)
            if fr is not None:
                frames.append(fr)
        frames = sorted(set(frames), reverse=True)  # rückwärts löschen
        for fr in frames:
            try:
                if hasattr(track.markers, 'delete_frame'):
                    track.markers.delete_frame(fr)
            except Exception:
                pass
    except Exception:
        pass
    return len(track.markers) == 0

# Track-orientierte API: Löscht den gesamten Track oder (Fallback) alle Marker
def run(track):
    clip = bpy.context.edit_movieclip
    if not clip:
        _log('kein aktiver Clip')
        return False
    name = getattr(track, 'name', None)
    before_names = [t.name for t in clip.tracking.tracks]
    _log(f'Vorher Tracks: {before_names}')

    # Zielobjekt ermitteln (Identität oder Name)
    target = None
    for t in clip.tracking.tracks:
        if t == track:
            target = t
            break
    if target is None and name:
        for t in clip.tracking.tracks:
            if t.name == name:
                target = t
                break
    if target is None:
        _log(f'Track {name} nicht gefunden – Abbruch')
        return False

    # Selektion zurücksetzen
    try:
        for t in clip.tracking.tracks:
            try:
                t.select = False
            except Exception:
                pass
        try:
            target.select = True
        except Exception:
            pass
    except Exception:
        _log('Fehler beim Selektionsreset')

    override = _build_override_for_clip(clip)
    _log(f'Override gefunden: {bool(override)}')
    if override:
        oa = override.get('area'); orr = override.get('region'); osp = override.get('space_data')
        _log(f'Override Details area={getattr(oa, "type", None)} region={getattr(orr, "type", None)} space_clip_ok={getattr(osp, "clip", None) == clip}')

    # Operator versuchen
    op_result = None
    try:
        if override:
            op_result = bpy.ops.clip.delete_track(override)
        else:
            op_result = bpy.ops.clip.delete_track()
        _log(f'Operator Ergebnis: {op_result}')
    except Exception as e:
        _log(f'Operator Exception: {e}')

    after_names = [t.name for t in clip.tracking.tracks]
    _log(f'Nachher Tracks: {after_names}')
    if name not in after_names:
        _log(f'Track {name} entfernt (Operator)')
        return True

    _log('Operator hat Track nicht entfernt -> Fallback Marker-Wipe')
    # Fallback: alle Marker löschen und erneut probieren
    wiped = _manual_track_wipe(target)
    _log(f'Marker-Wipe Erfolg={wiped} verbleibende Marker={len(target.markers) if target in clip.tracking.tracks else "?"}')
    if wiped:
        # Nochmal Operator
        try:
            if override:
                op_result = bpy.ops.clip.delete_track(override)
            else:
                op_result = bpy.ops.clip.delete_track()
            _log(f'Operator nach Wipe Ergebnis: {op_result}')
        except Exception as e:
            _log(f'Operator Exception nach Wipe: {e}')
        after2 = [t.name for t in clip.tracking.tracks]
        _log(f'Nachher2 Tracks: {after2}')
        if name not in after2:
            _log(f'Track {name} entfernt (Fallback)')
            return True

    # Letzter Ausweg: Umbenennen zur Sichtbarmachung
    try:
        new_name = f'FAILED_DEL_{name}' if name else 'FAILED_DEL'
        target.name = new_name
        _log(f'Track Umbenannt -> {new_name}')
    except Exception:
        pass
    _log(f'Entfernen von {name} endgültig fehlgeschlagen')
    return False
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
