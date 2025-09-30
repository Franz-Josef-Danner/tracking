"""Bereinigter Helper für Multi-Pass Feature Detection.

Diese Datei ist die konsolidierte finale Version ohne Duplikate.
"""

from __future__ import annotations

try:
    import bpy  # type: ignore
except ImportError:  # außerhalb Blender
    bpy = None  # type: ignore


def find_clip_editor_area(context):
    if bpy is None:
        return None
    for window in context.window_manager.windows:
        scr = window.screen
        if not scr:
            continue
        area = next((a for a in scr.areas if a.type == 'CLIP_EDITOR'), None)
        if area:
            return area
    return None


def get_clip_from_area(area):
    if area is None:
        return None
    try:
        return area.spaces.active.clip
    except Exception:  # noqa: BLE001
        return None


def _get_marker_on_frame(track, frame):
    if frame is not None:
        for m in track.markers:
            if m.frame == frame:
                return m
    if track.markers:
        return track.markers[0]
    return None


def detect_features_multipass(
    context,
    start_threshold: float = 1.0,
    min_threshold: float = 0.0001,
    factor: float = 0.5,
    max_passes: int = 32,
):
    if bpy is None:
        return {"success": False, "message": "bpy nicht verfügbar"}

    area = find_clip_editor_area(context)
    if area is None:
        return {"success": False, "message": "Kein Movie Clip Editor Bereich gefunden."}
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return {"success": False, "message": "Keine WINDOW Region gefunden."}

    clip = get_clip_from_area(area)
    if clip is None:
        return {"success": False, "message": "Kein Clip aktiv."}

    w = h = None
    try:
        w, h = clip.size
        print(f"[TrackingHelper] Clip Breite (px): {w}")
    except Exception:  # noqa: BLE001
        pass

    pattern_size = max(3, int(round((w or 0) * 0.01))) if w else 16
    search_size = pattern_size * 2

    settings = getattr(clip.tracking, 'settings', None)
    old_pattern = getattr(settings, 'default_pattern_size', None) if settings and hasattr(settings, 'default_pattern_size') else None
    old_search = getattr(settings, 'default_search_size', None) if settings and hasattr(settings, 'default_search_size') else None
    if settings is not None:
        try:
            if hasattr(settings, 'default_pattern_size'):
                settings.default_pattern_size = pattern_size
            if hasattr(settings, 'default_search_size'):
                settings.default_search_size = search_size
            print(f"[TrackingHelper] Set pattern_size={pattern_size} search_size={search_size}")
        except Exception:  # noqa: BLE001
            pass

    has_threshold = False
    try:
        rna = bpy.ops.clip.detect_features.get_rna_type()
        has_threshold = 'threshold' in rna.properties.keys()
    except Exception:  # noqa: BLE001
        has_threshold = False

    base_track_ids = {id(t) for t in clip.tracking.tracks}
    accepted_positions = []
    cur_frame_init = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
    if w and h:
        for t in clip.tracking.tracks:
            m = _get_marker_on_frame(t, cur_frame_init)
            if m is not None:
                co = m.co
                accepted_positions.append((co[0]*w, co[1]*h))

    per_pass = []
    marker_logs = []
    removed_markers = 0
    passes = 0
    thr = start_threshold
    cur_pattern_progressive = float(pattern_size)

    def apply_sizes(pat: float):
        nonlocal pattern_size, search_size
        p = max(3, int(round(pat)))
        s = p * 2
        if settings is not None:
            try:
                if hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = p
                if hasattr(settings, 'default_search_size'):
                    settings.default_search_size = s
            except Exception:  # noqa: BLE001
                pass
        pattern_size = p
        search_size = s

    def run_detect(current_thr: float):
        prev_count = len(clip.tracking.tracks)
        note = ''
        try:
            if has_threshold:
                bpy.ops.clip.detect_features(threshold=current_thr)
            else:
                bpy.ops.clip.detect_features()
                note = 'no-threshold'
        except TypeError:
            bpy.ops.clip.detect_features()
            note = 'TypeError->no-threshold'
        except Exception as e:  # noqa: BLE001
            return 0, f'error:{e}'
        return len(clip.tracking.tracks) - prev_count, note

    def process_new(pass_index: int, current_thr: float):
        nonlocal removed_markers
        new_tracks = [t for t in clip.tracking.tracks if id(t) not in base_track_ids]
        if not new_tracks:
            return 0
        cur_frame = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
        accepted_this_pass = 0
        limit = float(pattern_size)
        for t in new_tracks:
            m = _get_marker_on_frame(t, cur_frame)
            frame_used = None
            pos_norm = None
            pos_px = None
            if m is not None:
                frame_used = m.frame
                pos_norm = tuple(m.co)
                if w and h:
                    pos_px = (pos_norm[0]*w, pos_norm[1]*h)
            too_close = False
            if pos_px and accepted_positions:
                mx, my = pos_px
                for (ax, ay) in accepted_positions:
                    dx = mx - ax
                    dy = my - ay
                    if (dx*dx + dy*dy) ** 0.5 < limit:
                        too_close = True
                        break
            if too_close and frame_used is not None:
                try:
                    t.markers.delete_frame(frame_used)
                    removed_markers += 1
                    print(f"[TrackingHelper] Pass {pass_index} thr {current_thr:.5f} MARKER gelöscht track='{t.name}' frame={frame_used} pos_px={pos_px} (dist < {limit})")
                    marker_logs.append({
                        'pass': pass_index,
                        'threshold': current_thr,
                        'track_name': t.name,
                        'frame': frame_used,
                        'pos_norm': pos_norm,
                        'pos_px': pos_px,
                        'pattern': pattern_size,
                        'search': search_size,
                        'filtered': True,
                        'reason': f'dist < pattern_size ({limit})'
                    })
                    if len(t.markers) == 0:
                        try:
                            clip.tracking.tracks.remove(t)
                            print(f"[TrackingHelper] Track '{t.name}' entfernt (leer)")
                        except Exception:  # noqa: BLE001
                            pass
                    continue
                except Exception:  # noqa: BLE001
                    pass
            if pos_px:
                accepted_positions.append(pos_px)
            accepted_this_pass += 1
            print(f"[TrackingHelper] Pass {pass_index} thr {current_thr:.5f} NEUER MARKER track='{t.name}' frame={frame_used} pos_px={pos_px} pattern={pattern_size}")
            marker_logs.append({
                'pass': pass_index,
                'threshold': current_thr,
                'track_name': t.name,
                'frame': frame_used,
                'pos_norm': pos_norm,
                'pos_px': pos_px,
                'pattern': pattern_size,
                'search': search_size,
                'filtered': False
            })
        base_track_ids.update({id(t) for t in new_tracks})
        return accepted_this_pass

    try:
        try:
            with context.temp_override(area=area, region=region):
                while thr >= min_threshold and passes < max_passes:
                    apply_sizes(cur_pattern_progressive)
                    added_raw, note = run_detect(thr)
                    process_new(passes + 1, thr)
                    per_pass.append((thr, added_raw, note))
                    passes += 1
                    thr *= factor
                    cur_pattern_progressive *= 1.15  # Beibehalten!
        except AttributeError:
            while thr >= min_threshold and passes < max_passes:
                apply_sizes(cur_pattern_progressive)
                added_raw, note = run_detect(thr)
                process_new(passes + 1, thr)
                per_pass.append((thr, added_raw, note))
                passes += 1
                thr *= factor
                cur_pattern_progressive *= 1.5
    except Exception as e:  # noqa: BLE001
        return {
            'success': False,
            'message': f'Fehler: {e}',
            'passes': passes,
            'total_added': -1,
            'per_pass': per_pass,
            'pattern_size': pattern_size,
            'search_size': search_size,
            'marker_logs': marker_logs,
            'removed': removed_markers
        }
    finally:
        if settings is not None:
            try:
                if old_pattern is not None and hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = old_pattern
                if old_search is not None and hasattr(settings, 'default_search_size'):
                    settings.default_search_size = old_search
            except Exception:  # noqa: BLE001
                pass

    accepted_count = sum(1 for m in marker_logs if not m.get('filtered'))
    total_added_est = accepted_count + removed_markers

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added_est,
        'per_pass': per_pass,
        'pattern_size': pattern_size,
        'search_size': search_size,
        'marker_logs': marker_logs,
        'removed': removed_markers
    }

    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return {"success": False, "message": "Keine gültige WINDOW Region im Clip Editor gefunden."}

    clip = get_clip_from_area(area)
    if clip is None:
        return {"success": False, "message": "Kein Clip geladen."}

    # Auflösung
    w = h = None
    try:
        w, h = clip.size
        print(f"[TrackingHelper] Clip Breite (px): {w}")
    except Exception:  # noqa: BLE001
        pass

    pattern_size = None
    search_size = None
    settings = getattr(clip.tracking, 'settings', None)
    old_pattern = getattr(settings, 'default_pattern_size', None) if settings and hasattr(settings, 'default_pattern_size') else None
    old_search = getattr(settings, 'default_search_size', None) if settings and hasattr(settings, 'default_search_size') else None

    if w is not None:
        pattern_size = max(3, int(round(w * 0.01)))
        search_size = pattern_size * 2
        if settings is not None:
            try:
                if hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = pattern_size
                if hasattr(settings, 'default_search_size'):
                    settings.default_search_size = search_size
                print(f"[TrackingHelper] Set pattern_size={pattern_size}, search_size={search_size}")
            except Exception:  # noqa: BLE001
                pass

    # Threshold-Unterstützung prüfen
    has_threshold = False
    if bpy is not None:
        try:
            rna = bpy.ops.clip.detect_features.get_rna_type()
            has_threshold = 'threshold' in rna.properties.keys()
        except Exception:  # noqa: BLE001
            has_threshold = False

    per_pass = []  # (threshold, added, note)
    passes = 0
    current_thr = start_threshold

    # Track IDs / akzeptierte Positionen
    existing_track_ids = {id(t) for t in clip.tracking.tracks} if bpy is not None else set()
    accepted_positions = []  # (x_px, y_px)
    # Initial vorhandene Marker-Positionen sammeln
    if bpy is not None and w is not None and h is not None:
        cur_frame_init = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
        for t in clip.tracking.tracks:
            marker = None
            if cur_frame_init is not None:
                for m in t.markers:
                    if m.frame == cur_frame_init:
                        marker = m
                        break
            if marker is None and len(t.markers) > 0:
                marker = t.markers[0]
            if marker is not None:
                co = marker.co
                accepted_positions.append((co[0]*w, co[1]*h))

    marker_logs = []  # detaillierte Einträge inkl. gefiltert Flag
    removed_markers = 0

    def apply_sizes(cur_pattern):
        nonlocal pattern_size, search_size
        if settings is None:
            return
        try:
            p = max(3, int(round(cur_pattern)))
            s = p * 2
            if hasattr(settings, 'default_pattern_size'):
                settings.default_pattern_size = p
            if hasattr(settings, 'default_search_size'):
                settings.default_search_size = s
            pattern_size = p
            search_size = s
        except Exception:  # noqa: BLE001
            pass

    def run_detect(thr):
        """Führt detect aus, liefert (added, note)."""
        if bpy is None:
            return 0, 'kein bpy'
        prev_count = len(clip.tracking.tracks)
        note = ''
        try:
            if has_threshold:
                bpy.ops.clip.detect_features(threshold=thr)
            else:
                bpy.ops.clip.detect_features()
                note = 'no-threshold'
        except TypeError:
            bpy.ops.clip.detect_features()
            note = 'TypeError->no-threshold'
        except Exception as e:  # noqa: BLE001
            return 0, f'error:{e}'
        new_count = len(clip.tracking.tracks)
        return new_count - prev_count, note

    def process_new(pass_index, thr):
        """Logge neue Marker & wende Distanzfilter an (pattern_size)."""
        nonlocal existing_track_ids, accepted_positions, removed_markers
        if bpy is None:
            return 0
        cur_ids = {id(t) for t in clip.tracking.tracks}
        new_ids = cur_ids - existing_track_ids
        if not new_ids:
            return 0
        cur_frame = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
        min_dist = float(pattern_size) if pattern_size is not None else 0.0
        accepted_in_pass = 0
        for t in [t for t in clip.tracking.tracks if id(t) in new_ids]:
            marker = None
            frame_used = None
            pos_norm = None
            pos_px = None
            try:
                if cur_frame is not None:
                    for m in t.markers:
                        if m.frame == cur_frame:
                            marker = m
                            break
                if marker is None and len(t.markers) > 0:
                    marker = t.markers[0]
                if marker is not None:
                    frame_used = marker.frame
                    pos_norm = tuple(marker.co)
                    if w is not None and h is not None:
                        pos_px = (pos_norm[0]*w, pos_norm[1]*h)
            except Exception:  # noqa: BLE001
                pass

            # Distanzprüfung
            too_close = False
            offending = None
            if pos_px is not None and min_dist > 0 and accepted_positions:
                mx, my = pos_px
                for (ax, ay) in accepted_positions:
                    dx = mx - ax
                    dy = my - ay
                    if (dx*dx + dy*dy) ** 0.5 < min_dist:
                        too_close = True
                        offending = (ax, ay)
                        break
            if too_close and frame_used is not None:
                try:
                    t.markers.delete_frame(frame_used)
                    removed_markers += 1
                    print(f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} MARKER gelöscht (dist<{min_dist}px) track='{t.name}' frame={frame_used} pos_px={pos_px} ref={offending}")
                    marker_logs.append({
                        'pass': pass_index,
                        'threshold': thr,
                        'track_name': t.name,
                        'frame': frame_used,
                        'pos_norm': pos_norm,
                        'pos_px': pos_px,
                        'pattern': pattern_size,
                        'search': search_size,
                        'filtered': True,
                        'reason': f'abstand < pattern_size ({min_dist})'
                    })
                    if len(t.markers) == 0:
                        try:
                            clip.tracking.tracks.remove(t)
                            print(f"[TrackingHelper] Track '{t.name}' entfernt (leer)")
                        except Exception:  # noqa: BLE001
                            pass
                    continue
                except Exception:  # noqa: BLE001
                    pass

            # akzeptiert
            if pos_px is not None:
                accepted_positions.append(pos_px)
            accepted_in_pass += 1
            print(f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} NEUER MARKER track='{t.name}' frame={frame_used} pos_px={pos_px} pattern={pattern_size}")
            marker_logs.append({
                'pass': pass_index,
                'threshold': thr,
                'track_name': t.name,
                'frame': frame_used,
                'pos_norm': pos_norm,
                'pos_px': pos_px,
                'pattern': pattern_size,
                'search': search_size,
                'filtered': False
            })
        existing_track_ids.update(new_ids)
        return accepted_in_pass

    try:
        try:
            if bpy is None:
                raise RuntimeError('bpy nicht verfügbar')
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    if pattern_size is not None:
                        apply_sizes(pattern_size)
                    added, note = run_detect(current_thr)
                    process_new(1, current_thr)
                    per_pass.append((current_thr, added, note or 'no-threshold'))
                    passes = 1
                else:
                    cur_pattern_progressive = float(pattern_size) if pattern_size else None
                    while current_thr >= min_threshold and passes < max_passes:
                        if cur_pattern_progressive is not None:
                            apply_sizes(cur_pattern_progressive)
                        added, note = run_detect(current_thr)
                        process_new(passes+1, current_thr)
                        per_pass.append((current_thr, added, note))
                        passes += 1
                        current_thr *= factor
                        if cur_pattern_progressive is not None:
                            cur_pattern_progressive *= 1.15  # NICHT ÄNDERN – Wunsch beibehalten
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            if not has_threshold:
                if pattern_size is not None:
                    apply_sizes(pattern_size)
                added, note = run_detect(current_thr)
                process_new(1, current_thr)
                per_pass.append((current_thr, added, note or 'no-threshold'))
                passes = 1
            else:
                cur_pattern_progressive = float(pattern_size) if pattern_size else None
                while current_thr >= min_threshold and passes < max_passes:
                    if cur_pattern_progressive is not None:
                        apply_sizes(cur_pattern_progressive)
                    added, note = run_detect(current_thr)
                    process_new(passes+1, current_thr)
                    per_pass.append((current_thr, added, note))
                    passes += 1
                    current_thr *= factor
                    if cur_pattern_progressive is not None:
                        cur_pattern_progressive *= 1.5  # Fallback kann aggressiver skalieren
    except Exception as e:  # noqa: BLE001
        return {
            'success': False,
            'message': f'Fehler: {e}',
            'passes': passes,
            'total_added': -1,
            'per_pass': per_pass,
            'pattern_size': pattern_size,
            'search_size': search_size,
            'marker_logs': marker_logs,
            'removed': removed_markers
        }
    finally:
        # Restore Settings
        if settings is not None:
            try:
                if old_pattern is not None and hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = old_pattern
                if old_search is not None and hasattr(settings, 'default_search_size'):
                    settings.default_search_size = old_search
            except Exception:  # noqa: BLE001
                pass

    total_added = len(clip.tracking.tracks) if bpy is not None else -1
    if total_added >= 0 and passes > 0:
        total_added -= len(existing_track_ids)  # approximativ neu (nach evtl. Entfernen)

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'per_pass': per_pass,
        'pattern_size': pattern_size,
        'search_size': search_size,
        'marker_logs': marker_logs,
        'removed': removed_markers
    }

try:  # Blender Umgebung
    import bpy  # type: ignore
except ImportError:  # außerhalb Blender
    bpy = None  # type: ignore


def find_clip_editor_area(context):
    for window in context.window_manager.windows:
        scr = window.screen
        if not scr:
            continue
        area = next((a for a in scr.areas if a.type == 'CLIP_EDITOR'), None)
        if area:
            return area
    return None


    def log_new_tracks(pass_index, thr):
    try:
        return area.spaces.active.clip
    except Exception:  # noqa: BLE001
        return None


def detect_features_multipass(context, start_threshold=1.0, min_threshold=0.0001, factor=0.5, max_passes=32):
    """Führt mehrfache Feature-Erkennung aus.

    Returns:
        dict mit Schlüsseln:
            success (bool)
            message (str)
            passes (int)
            total_added (int | -1)
            per_pass (list[tuple(threshold, added, note)])
    """
    area = find_clip_editor_area(context)
    if area is None:
        return {
            'success': False,
            'message': 'Kein Movie Clip Editor Bereich gefunden (öffne einen Clip Editor).'
        }
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return {
            'success': False,
            'message': 'Keine gültige WINDOW Region im Clip Editor gefunden.'
        }

    clip = get_clip_from_area(area)
    pattern_size = None
                # Distanzschwelle = aktuelle pattern_size (Pixel)
                min_dist = float(pattern_size) if pattern_size is not None else 0.0
                too_close = False
                offending_ref = None
                if marker_px is not None and min_dist > 0 and accepted_positions:
                    mx, my = marker_px
                    for (ax, ay) in accepted_positions:
                        dx = mx - ax
                        dy = my - ay
                        if (dx*dx + dy*dy) ** 0.5 < min_dist:
                            too_close = True
                            offending_ref = (ax, ay)
                            break
                if too_close and frame_used is not None:
                    try:
                        # Nur Marker am Frame löschen, nicht zwingend gesamten Track
                        t.markers.delete_frame(frame_used)
                        removed_total += 1
                        print(
                            f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} MARKER von TRACK '{t.name}' gelöscht (Abstand < {min_dist}px) "
                            f"pos_px={marker_px} ref={offending_ref} frame={frame_used}"
                        )
                        marker_logs.append({
                            'pass': pass_index,
                            'threshold': thr,
                            'track_name': t.name,
                            'frame': frame_used,
                            'pos_norm': marker_co_norm,
                            'pos_px': marker_px,
                            'pattern': pattern_size,
                            'search': search_size,
                            'filtered': True,
                            'reason': f'abstand < pattern_size ({min_dist})'
                        })
                        # Falls der Track keine Marker mehr hat -> Track entfernen
                        if len(t.markers) == 0:
                            try:
                                clip.tracking.tracks.remove(t)
                                print(f"[TrackingHelper] Track '{t.name}' entfernt (leer nach Marker-Löschung)")
                            except Exception:  # noqa: BLE001
                                pass
                        continue
                    except Exception:  # noqa: BLE001
                        pass

                # Marker akzeptiert
                count += 1
                if marker_px is not None:
                    accepted_positions.append(marker_px)
                print(
                    f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} NEUER MARKER TRACK '{t.name}' "
                    f"frame={frame_used} pos_norm={marker_co_norm} pos_px={marker_px} pattern={pattern_size} search={search_size}"
                )
                marker_logs.append({
                    'pass': pass_index,
                    'threshold': thr,
                    'track_name': t.name,
                    'frame': frame_used,
                    'pos_norm': marker_co_norm,
                    'pos_px': marker_px,
                    'pattern': pattern_size,
                    'search': search_size,
                    'filtered': False
                })
    marker_logs = []  # speichert detailinformationen neuer Marker
    existing_track_ids = set()
    accepted_positions = []  # Liste bereits akzeptierter (x_px, y_px) Positionen
    if clip and bpy is not None:
        existing_track_ids = {id(t) for t in clip.tracking.tracks}
        # Initiale Positionen vorhandener Tracks sammeln
        try:
            if w is not None and h is not None:
                cur_frame_init = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
                for t in clip.tracking.tracks:
                    marker = None
                    if cur_frame_init is not None:
                        for m in t.markers:
                            if m.frame == cur_frame_init:
                                marker = m
                                break
                    if marker is None and len(t.markers) > 0:
                        marker = t.markers[0]
                    if marker is not None:
                        co = marker.co
                        accepted_positions.append((co[0]*w, co[1]*h))
        except Exception:  # noqa: BLE001
            pass

    def apply_sizes(cur_pattern):
        """Setzt pattern/search size auf Basis cur_pattern."""
        if settings is None:
            return
        try:
            p = max(3, int(round(cur_pattern)))
            s = p * 2
            if hasattr(settings, 'default_pattern_size'):
                settings.default_pattern_size = p
            if hasattr(settings, 'default_search_size'):
                settings.default_search_size = s
            # für Rückgabe aktualisieren (letzte Werte)
            nonlocal pattern_size, search_size
            pattern_size = p
            search_size = s
        except Exception:  # noqa: BLE001
            pass

    def run_detect(thr, allow_param=True):
        prev_count = len(clip.tracking.tracks) if (clip and bpy is not None) else 0
        note = ''
        try:
            if bpy is None:
                return 0, 'kein bpy (Entwicklungsumgebung)'
            if has_threshold and allow_param:
                bpy.ops.clip.detect_features(threshold=thr)
            else:
                bpy.ops.clip.detect_features()
                if allow_param and not has_threshold:
                    note = 'threshold nicht unterstützt'
        except TypeError:
            if bpy is not None:
                bpy.ops.clip.detect_features()
            note = 'TypeError threshold'
        new_total = len(clip.tracking.tracks) if (clip and bpy is not None) else prev_count
        return new_total - prev_count, note

    removed_total = 0

    def log_new_tracks(pass_index, thr):
        if not (clip and bpy is not None):
            return 0
        nonlocal existing_track_ids
        nonlocal removed_total
        nonlocal accepted_positions
        cur_ids = {id(t) for t in clip.tracking.tracks}
        new_ids = cur_ids - existing_track_ids
        if not new_ids:
            return 0
        cur_frame = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
        count = 0
        # Liste der tatsächlich neuen Track Objekte
        new_tracks = [t for t in clip.tracking.tracks if id(t) in new_ids]
        # Für Distanzvergleich: current_search_size (Pixel) = search_size (bereits px) oder fallback
        min_dist = float(search_size) if search_size is not None else 0.0
        for t in new_tracks:
            marker_co_norm = None
            marker_px = None
            frame_used = None
            try:
                marker = None
                if cur_frame is not None:
                    for m in t.markers:
                        if m.frame == cur_frame:
                            marker = m
                            break
                if marker is None and len(t.markers) > 0:
                    marker = t.markers[0]
                if marker is not None:
                    marker_co_norm = tuple(marker.co)
                    frame_used = marker.frame
                    if w is not None and h is not None:
                        marker_px = (marker_co_norm[0] * w, marker_co_norm[1] * h)
            except Exception:  # noqa: BLE001
                pass

            # Distanzprüfung nur wenn Pixelkoordinate vorhanden und min_dist > 0
            too_close = False
            if marker_px is not None and min_dist > 0 and accepted_positions:
                mx, my = marker_px
                for (ax, ay) in accepted_positions:
                    dx = mx - ax
                    dy = my - ay
                    if (dx*dx + dy*dy) ** 0.5 < min_dist:
                        too_close = True
                        break
            if too_close:
                try:
                    clip.tracking.tracks.remove(t)
                    removed_total += 1
                    print(
                        f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} TRACK '{t.name}' entfernt (Abstand < {min_dist}px) pos_px={marker_px}"
                    )
                except Exception:  # noqa: BLE001
                    pass
                continue

            # Track akzeptiert
            count += 1
            if marker_px is not None:
                accepted_positions.append(marker_px)
            print(
                f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} NEUER TRACK '{t.name}' "
                f"frame={frame_used} pos_norm={marker_co_norm} pos_px={marker_px} pattern={pattern_size} search={search_size}"
            )
            marker_logs.append({
                'pass': pass_index,
                'threshold': thr,
                'track_name': t.name,
                'frame': frame_used,
                'pos_norm': marker_co_norm,
                'pos_px': marker_px,
                'pattern': pattern_size,
                'search': search_size,
                'filtered': False
            })
        existing_track_ids.update(new_ids)
        return count

    try:
        try:
            # Prefer temp_override
            if bpy is None:
                raise RuntimeError('bpy nicht verfügbar')
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    # Set sizes für diesen Pass
                    apply_sizes(pattern_size)
                    added, note = run_detect(current, allow_param=False)
                    # Log erst nach Detect
                    log_new_tracks(passes + 1, current)
                    per_pass.append((current, added, note or 'kein threshold Param'))
                    passes = 1
                else:
                    cur_pattern_progressive = float(pattern_size) if pattern_size else None
                    while current >= min_threshold and passes < max_passes:
                        if cur_pattern_progressive is not None:
                            apply_sizes(cur_pattern_progressive)
                        added, note = run_detect(current, allow_param=True)
                        log_new_tracks(passes + 1, current)
                        per_pass.append((current, added, note))
                        passes += 1
                        current *= factor
                        if cur_pattern_progressive is not None:
                            cur_pattern_progressive *= 1.15
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            if not has_threshold:
                apply_sizes(pattern_size)
                # Verwende run_detect auch hier, um identisches Logging zu gewährleisten
                added, note = run_detect(current, allow_param=False)
                log_new_tracks(passes + 1, current)
                per_pass.append((current, added, note or 'fallback ohne threshold'))
                passes = 1
            else:
                cur_pattern_progressive = float(pattern_size) if pattern_size else None
                while current >= min_threshold and passes < max_passes:
                    if cur_pattern_progressive is not None:
                        apply_sizes(cur_pattern_progressive)
                    try:
                        added, note = run_detect(current, allow_param=True)
                        log_new_tracks(passes + 1, current)
                        per_pass.append((current, added, note or 'fallback'))
                    except Exception:  # noqa: BLE001
                        per_pass.append((current, 0, 'fallback Fehler'))
                        break
                    passes += 1
                    current *= factor
                    if cur_pattern_progressive is not None:
                        cur_pattern_progressive *= 1.5
    except Exception as e:  # noqa: BLE001
        return {
            'success': False,
            'message': f'Fehler: {e}',
            'passes': passes,
            'total_added': -1,
            'per_pass': per_pass,
            'pattern_size': pattern_size,
            'search_size': search_size,
            'marker_logs': marker_logs,
            'removed': removed_total
        }
    finally:
        # Ursprüngliche Werte wiederherstellen
        if settings is not None:
            try:
                if old_pattern is not None and hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = old_pattern
                if old_search is not None and hasattr(settings, 'default_search_size'):
                    settings.default_search_size = old_search
            except Exception:  # noqa: BLE001
                pass

    if clip:
        total_added = len(clip.tracking.tracks) - tracks_before
    else:
        total_added = -1

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'per_pass': per_pass,
        'pattern_size': pattern_size,
        'search_size': search_size,
        'marker_logs': marker_logs,
        'removed': removed_total
    }
