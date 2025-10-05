import bpy


def _resolve_track(context, track_name: str, case_insensitive: bool = True):
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print(f"[Kaiserlich Tracker][DEBUG] _resolve_track: Kein gültiger CLIP_EDITOR Kontext (space={getattr(space, 'type', None)})")
        return None
    clip = getattr(space, 'clip', None)
    if not clip:
        print("[Kaiserlich Tracker][DEBUG] _resolve_track: Kein aktiver Clip vorhanden.")
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
                print(f"[Kaiserlich Tracker][DEBUG] _resolve_track: Case-insensitive Match '{tr.name}' für Eingabe '{track_name}'")
                return tr
    print(f"[Kaiserlich Tracker][DEBUG] _resolve_track: Track '{track_name}' nicht gefunden. Verfügbare Tracks: {[t.name for t in tracking.tracks]}")
    return None


def _marker_frames(track):
    try:
        return sorted([m.frame for m in track.markers])
    except Exception:
        return []


def _debug_track_introspection(track):
    try:
        attrs = [a for a in dir(track.markers) if not a.startswith('_')]
        print(f"[Kaiserlich Tracker][INTROSPECT] track='{track.name}' markers_attrs={attrs}")
    except Exception as e:
        print(f"[Kaiserlich Tracker][INTROSPECT] Fehler beim Auflisten marker attrs -> {e}")
    try:
        print(f"[Kaiserlich Tracker][INTROSPECT] track='{track.name}' len(markers)={len(track.markers)} first_marker_frame={getattr(track.markers[0],'frame',None) if len(track.markers)>0 else None}")
    except Exception as e:
        print(f"[Kaiserlich Tracker][INTROSPECT] Fehler Basisdaten -> {e}")


def _remove_marker_object(track, marker):
    """Versucht Marker zu entfernen und verifiziert direkt den Effekt.
    Rückgabe: (removed_effective: bool, methode: str oder None)"""
    if marker is None:
        return False, None
    before_frames = _marker_frames(track)
    before_count = len(before_frames)
    marker_frame = getattr(marker, 'frame', None)

    available = [m for m in ("delete", "remove", "delete_frame") if hasattr(track.markers, m)]
    print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: Verfügbare Methoden={available} Track={track.name} MarkerFrame={marker_frame} VorherCount={before_count}")

    def verify(methode_name):
        after_frames = _marker_frames(track)
        after_count = len(after_frames)
        still = marker_frame in after_frames
        print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: Methode={methode_name} AfterCount={after_count} StillThere={still}")
        # Spezieller Fall: Letzter Marker einer Spur darf evtl. nicht verschwinden
        return (not still) or (before_count == 1 and after_count == 1 and still)

    if hasattr(track.markers, 'delete'):
        try:
            track.markers.delete(marker)
            if verify('delete(marker)'):
                return True, 'delete(marker)'
        except Exception as e:
            print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: delete(marker) FAIL -> {e}")
    if hasattr(track.markers, 'remove'):
        try:
            track.markers.remove(marker)
            if verify('remove(marker)'):
                return True, 'remove(marker)'
        except Exception as e:
            print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: remove(marker) FAIL -> {e}")
    if hasattr(track.markers, 'delete_frame') and marker_frame is not None:
        try:
            track.markers.delete_frame(marker_frame)
            if verify('delete_frame(frame)'):
                return True, 'delete_frame(frame)'
        except Exception as e:
            print(f"[Kaiserlich Tracker][DEBUG] _remove_marker_object: delete_frame(frame) FAIL -> {e}")

    print("[Kaiserlich Tracker][DEBUG] _remove_marker_object: Alle Methoden ohne effektive Entfernung.")
    return False, None


def delete_marker_frame(context, track_name: str, frame: int) -> bool:
    """Löscht einen einzelnen Marker-Keyframe eines Tracks (by frame) mit ausführlichem Debug-Log."""
    space = context.space_data
    if not space or space.type != 'CLIP_EDITOR':
        print("[Kaiserlich Tracker] delete_marker_frame: Kein CLIP_EDITOR Kontext.")
        return False
    clip = getattr(space, 'clip', None)
    if not clip:
        print("[Kaiserlich Tracker] delete_marker_frame: Kein aktiver Clip.")
        return False
    tracking = clip.tracking
    print(f"[Kaiserlich Tracker][DEBUG] delete_marker_frame: Ziel track='{track_name}' frame={frame} AktuelleSceneFrame={context.scene.frame_current}")
    print(f"[Kaiserlich Tracker][DEBUG] delete_marker_frame: Verfügbare Tracks={[t.name for t in tracking.tracks]}")
    try:
        for tr in tracking.tracks:
            if tr.name != track_name:
                continue
            frames_vorher = _marker_frames(tr)
            print(f"[Kaiserlich Tracker][DEBUG] Track '{tr.name}' MarkerFrames vor Löschung: {frames_vorher[:50]} (Total={len(frames_vorher)})")
            _debug_track_introspection(tr)

            # Marker suchen
            marker = None
            used_find = False
            if hasattr(tr.markers, 'find_frame'):
                try:
                    marker = tr.markers.find_frame(frame)
                    used_find = True
                except Exception as e:
                    print(f"[Kaiserlich Tracker][DEBUG] find_frame Exception -> {e}")
                    marker = None
            if marker is None:
                for m in tr.markers:
                    if getattr(m, 'frame', None) == frame:
                        marker = m
                        break
            if marker is None:
                print(f"[Kaiserlich Tracker] Marker nicht gefunden: track={track_name} frame={frame} (find_frame_verwendet={used_find})")
                return False
            print(f"[Kaiserlich Tracker][DEBUG] Gefundener Marker frame={getattr(marker,'frame',None)} used_find={used_find}")

            removed, methode = _remove_marker_object(tr, marker)
            print(f"[Kaiserlich Tracker][DEBUG] Entfernen Ergebnis removed_effective={removed} methode={methode}")

            still_there = any(m.frame == frame for m in tr.markers)
            frames_nachher = _marker_frames(tr)
            print(f"[Kaiserlich Tracker][DEBUG] Track '{tr.name}' MarkerFrames nach Löschung: {frames_nachher[:50]} (Total={len(frames_nachher)}) still_there={still_there}")

            # Sonderfall: Spur mit einzigem Marker lässt sich per API nicht leeren -> ggf. Track entfernen
            if still_there and len(frames_nachher) == 1 and removed:
                print(f"[Kaiserlich Tracker][DEBUG] Single-Marker-Track Fallback -> Entferne gesamten Track '{tr.name}'")
                try:
                    tr_parent = getattr(tr, 'track', None)
                    # Direktes Entfernen aus tracking.tracks
                    tracking.tracks.remove(tr)
                    print(f"[Kaiserlich Tracker] Track entfernt (wegen letztem Marker): {track_name}")
                    return True
                except Exception as e:
                    print(f"[Kaiserlich Tracker][DEBUG] Track-Remove FAIL -> {e}")

            if not still_there and removed:
                try:
                    context.scene.frame_set(context.scene.frame_current)
                except Exception as e:
                    print(f"[Kaiserlich Tracker][DEBUG] frame_set Exception -> {e}")
                print(f"[Kaiserlich Tracker] Marker gelöscht: track={track_name} frame={frame} via {methode}")
                return True
            print(f"[Kaiserlich Tracker] Marker konnte nicht gelöscht werden (track={track_name} frame={frame}) removed={removed} still_there={still_there} methode={methode}")
            if frames_nachher:
                diffs = [(abs(f - frame), f) for f in frames_nachher]
                diffs.sort()
                print(f"[Kaiserlich Tracker][DEBUG] Nächste vorhandene Markerframes relativ zum Ziel: {diffs[:5]}")

            # Operator-Fallback (nur wenn Frame noch existiert)
            if still_there:
                print("[Kaiserlich Tracker][DEBUG] Starte Operator-Fallback bpy.ops.clip.delete_marker() ...")
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
                except Exception as e:
                    print(f"[Kaiserlich Tracker][DEBUG] Fallback Kontextsuche Fehler -> {e}")

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
                    print(f"[Kaiserlich Tracker][DEBUG] Fallback Auswahl gesetzt: track='{tr.name}' frame={frame}")
                except Exception as e:
                    print(f"[Kaiserlich Tracker][DEBUG] Auswahl setzen Fehler -> {e}")

                try:
                    if override:
                        result = bpy.ops.clip.delete_marker(override)
                    else:
                        result = bpy.ops.clip.delete_marker()
                    print(f"[Kaiserlich Tracker][DEBUG] Operator Rückgabe: {result}")
                except Exception as e:
                    print(f"[Kaiserlich Tracker][DEBUG] Operator Fehler -> {e}")

                # Nach-Überprüfung
                frames_after_op = _marker_frames(tr)
                print(f"[Kaiserlich Tracker][DEBUG] Nach Operator Frames: {frames_after_op}")
                if frame not in frames_after_op:
                    print(f"[Kaiserlich Tracker] Marker gelöscht (Operator Fallback): track={track_name} frame={frame}")
                    return True
                else:
                    print(f"[Kaiserlich Tracker][DEBUG] Operator-Fallback ohne Erfolg für track={track_name} frame={frame}")
            return False
    except Exception as e:
        print(f"[Kaiserlich Tracker] Fehler beim Löschen Marker track={track_name} frame={frame}: {e}")
    return False


def delete_marker_index(context, track_name: str, index: int) -> bool:
    """Löscht Marker per Index (0-basiert in aktueller Reihenfolge der Collection) mit Debug."""
    tr = _resolve_track(context, track_name)
    if not tr:
        print(f"[Kaiserlich Tracker] Track nicht gefunden: {track_name}")
        return False
    markers_list = list(tr.markers)
    print(f"[Kaiserlich Tracker][DEBUG] delete_marker_index: Track={track_name} MarkerAnzahl={len(markers_list)} IndexZiel={index}")
    if index < 0 or index >= len(markers_list):
        print(f"[Kaiserlich Tracker] Ungültiger Marker-Index {index} (Track {track_name})")
        return False
    marker = markers_list[index]
    frame = getattr(marker, 'frame', None)
    removed, methode = _remove_marker_object(tr, marker)
    still_there = any(getattr(m, 'frame', None) == frame for m in tr.markers)
    if removed and not still_there:
        print(f"[Kaiserlich Tracker] Marker (Index {index}, Frame {frame}) gelöscht: {track_name} via {methode}")
        return True
    print(f"[Kaiserlich Tracker] Marker (Index {index}) NICHT gelöscht: {track_name} removed={removed} still_there={still_there} methode={methode}")
    return False


def delete_all_markers(context, track_name: str) -> int:
    """Löscht alle Marker eines Tracks und gibt Anzahl gelöschter Marker zurück (Debug)."""
    tr = _resolve_track(context, track_name)
    if not tr:
        print(f"[Kaiserlich Tracker] Track nicht gefunden: {track_name}")
        return 0
    original = _marker_frames(tr)
    print(f"[Kaiserlich Tracker][DEBUG] delete_all_markers: Track={track_name} StartFrames={original[:50]} Total={len(original)}")
    count = 0
    for mk in list(tr.markers):
        removed, methode = _remove_marker_object(tr, mk)
        if removed:
            count += 1
    remaining = _marker_frames(tr)
    print(f"[Kaiserlich Tracker] Alle Marker gelöscht: {track_name} (Entfernt={count} Vorher={len(original)} Rest={len(remaining)})")
    if remaining:
        print(f"[Kaiserlich Tracker][DEBUG] Verbliebene Frames: {remaining[:50]}")
    return count
