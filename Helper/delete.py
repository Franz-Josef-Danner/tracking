import bpy


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

            # Sonderfall: Spur mit einzigem Marker lässt sich per API nicht leeren -> versuche Track direkt zu löschen (ohne Dummy-Marker)
            if still_there and len(frames_nachher) == 1 and removed:
                deleted_track = False
                try:
                    for tsel in tracking.tracks:
                        try:
                            tsel.select = False
                        except Exception:
                            pass
                    try:
                        tr.select = True
                    except Exception:
                        pass
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
                    deleted_track = all(t.name != tr.name for t in tracking.tracks)
                except Exception:
                    pass
                if deleted_track:
                    return True

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
