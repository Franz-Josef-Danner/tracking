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


def get_clip_from_area(area):
    try:
        return area.spaces.active.clip
    except Exception:  # noqa: BLE001
        return None


def detect_features_multipass(context, start_threshold=1.0, min_threshold=0.1, factor=0.5, max_passes=32):
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
    search_size = None
    old_pattern = None
    old_search = None
    settings = None
    w = None
    h = None
    if clip:
        try:
            w, h = clip.size
            print(f"[TrackingHelper] Clip Breite (px): {w}")
            # Berechnung gemäß Anforderung:
            # pattern_size = horizontale Auflösung * 0.01
            pattern_size = max(3, int(round(w * 0.01)))
            search_size = pattern_size * 2
            settings = getattr(clip.tracking, 'settings', None)
            if settings is not None:
                # Alte Werte sichern
                old_pattern = getattr(settings, 'default_pattern_size', None)
                old_search = getattr(settings, 'default_search_size', None)
                # Setzen falls Attribute vorhanden
                if hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = pattern_size
                if hasattr(settings, 'default_search_size'):
                    settings.default_search_size = search_size
                print(f"[TrackingHelper] Set pattern_size={pattern_size}, search_size={search_size}")
        except Exception:  # noqa: BLE001
            pass
    tracks_before = len(clip.tracking.tracks) if clip else -1

    # Prüfen ob threshold unterstützt wird
    has_threshold = False
    if bpy is not None:
        try:
            rna = bpy.ops.clip.detect_features.get_rna_type()
            has_threshold = 'threshold' in rna.properties.keys()
        except Exception:  # noqa: BLE001
            has_threshold = False

    per_pass = []
    passes = 0
    current = start_threshold
    marker_logs = []  # speichert detailinformationen neuer Marker
    existing_track_ids = set()
    if clip and bpy is not None:
        existing_track_ids = {id(t) for t in clip.tracking.tracks}

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

    def log_new_tracks(pass_index, thr):
        if not (clip and bpy is not None):
            return 0
        nonlocal existing_track_ids
        cur_ids = {id(t) for t in clip.tracking.tracks}
        new_ids = cur_ids - existing_track_ids
        if not new_ids:
            return 0
        cur_frame = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
        # NEU: Wir verwenden primär alle zuvor geloggten Marker-Positionen (marker_logs),
        # damit auch bei Blender-Replacements (IDs ändern sich) die Distanz-Basis erhalten bleibt.
        # Zusätzlich sammeln wir – falls verfügbar – die realen existierenden Track-Objekt-Positionen.
        existing_positions_px = []  # inkrementell erweitert, auch innerhalb dieses Passes
        fallback_used = False
        if w is not None and h is not None:
            try:
                # Basis aus allen zuvor geloggten Markern (Pass < aktueller Pass)
                if marker_logs:
                    existing_positions_px.extend([m['pos_px'] for m in marker_logs if m.get('pos_px')])
                # Ergänzend: aktuelle Track-Objekte, die nicht neu sind (sofern Blender sie nicht ersetzt hat)
                for t in clip.tracking.tracks:
                    if id(t) in existing_track_ids:
                        marker_ref = None
                        if cur_frame is not None:
                            for mm in t.markers:
                                if mm.frame == cur_frame:
                                    marker_ref = mm
                                    break
                        if marker_ref is None and len(t.markers) > 0:
                            marker_ref = t.markers[0]
                        if marker_ref is not None:
                            co_norm = marker_ref.co
                            existing_positions_px.append((co_norm[0] * w, co_norm[1] * h))
                # Falls immer noch leer (kein einziger früherer Marker), bekommen die ersten neuen Marker keine Distanz.
                if not existing_positions_px:
                    fallback_used = True  # markiere nur zur Info
            except Exception:  # noqa: BLE001
                fallback_used = True
        count = 0
        for t in clip.tracking.tracks:
            if id(t) in new_ids:
                count += 1
                marker_co_norm = None
                marker_px = None
                frame_used = None
                nearest_dist_px = None
                replaced_name = False
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
                            # Distanz zu allen vorhandenen (bisherigen) Marker-Positionen berechnen
                            if existing_positions_px:
                                try:
                                    x, y = marker_px
                                    nearest_dist_px = min(((x - ex) ** 2 + (y - ey) ** 2) for ex, ey in existing_positions_px) ** 0.5
                                except Exception:  # noqa: BLE001
                                    nearest_dist_px = None
                            # Aktuellen Marker sofort zu Basis hinzufügen, damit spätere Marker IN DIESEM PASS
                            # ihre Distanz auch zu ihm berechnen können.
                            existing_positions_px.append(marker_px)
                    # Prüfen, ob Track-Name schon früher existierte (ersetzt / dupliziert); nur für Analysezwecke
                    if marker_logs and any(m['track_name'] == t.name for m in marker_logs):
                        replaced_name = True
                except Exception:  # noqa: BLE001
                    pass
                no_distance_reason = None
                if nearest_dist_px is None:
                    if marker_px is None:
                        no_distance_reason = 'no_marker_position'
                    elif not existing_positions_px or (len(existing_positions_px) == 1 and existing_positions_px[-1] == marker_px):
                        # Nur der aktuelle Marker vorhanden -> keine Vergleichsbasis
                        no_distance_reason = 'no_reference_positions'
                    else:
                        no_distance_reason = 'calc_error'
                print(
                    f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} NEUER TRACK '{t.name}' "
                    f"frame={frame_used} pos_norm={marker_co_norm} pos_px={marker_px} nearest_px={nearest_dist_px} pattern={pattern_size} search={search_size}"
                )
                marker_logs.append({
                    'pass': pass_index,
                    'threshold': thr,
                    'track_name': t.name,
                    'frame': frame_used,
                    'pos_norm': marker_co_norm,
                    'pos_px': marker_px,
                    'nearest_dist_px': nearest_dist_px,
                    'pattern': pattern_size,
                    'search': search_size,
                    'distance_fallback': fallback_used,
                    'replaced_name': replaced_name,
                    'no_distance_reason': no_distance_reason,
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
            'marker_logs': marker_logs
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

    # Distanz-Statistiken berechnen (global & pro Pass), um Transparenz zu schaffen
    def _compute_stats(values):
        if not values:
            return {'count': 0, 'min': None, 'max': None, 'mean': None, 'median': None}
        s = sorted(values)
        n = len(s)
        mean = sum(s) / n
        if n % 2:
            median = s[n // 2]
        else:
            median = 0.5 * (s[n // 2 - 1] + s[n // 2])
        return {
            'count': n,
            'min': s[0],
            'max': s[-1],
            'mean': mean,
            'median': median,
        }

    distances_all = [m['nearest_dist_px'] for m in marker_logs if m.get('nearest_dist_px') is not None]
    distance_stats = _compute_stats(distances_all)
    distances_per_pass = {}
    per_pass_stats = {}
    for m in marker_logs:
        if m.get('nearest_dist_px') is None:
            continue
        p = m['pass']
        distances_per_pass.setdefault(p, []).append(m['nearest_dist_px'])
    for p, vals in distances_per_pass.items():
        per_pass_stats[p] = _compute_stats(vals)

    # Zusatz-Metriken: Zero-Distanzen (Marker exakt auf bestehender Position) sind erwartungsgemäß häufig
    zero_count = sum(1 for d in distances_all if d == 0.0)
    positive_distances = [d for d in distances_all if d and d > 0.0]
    min_positive = min(positive_distances) if positive_distances else None
    positive_count = len(positive_distances)
    zero_ratio = (zero_count / len(distances_all)) if distances_all else None

    # Kurze Ausgabe zur Orientierung
    try:
        print(
            f"[TrackingHelper] Distanz Statistik gesamt: count={distance_stats['count']} min={distance_stats['min']} max={distance_stats['max']} "
            f"median={distance_stats['median']} mean={distance_stats['mean']}")
        if distances_all:
            print(
                f"[TrackingHelper] Distanz Verteilung: zeros={zero_count} ({zero_ratio:.2%} ) >0={positive_count} min_pos={min_positive}"
            )
        # Zusatz: Gründe für fehlende Distanzen, falls Diskrepanz auffällig
        missing = [m for m in marker_logs if m.get('nearest_dist_px') is None]
        if missing:
            reason_counter = {}
            for m in missing:
                r = m.get('no_distance_reason') or 'unknown'
                reason_counter[r] = reason_counter.get(r, 0) + 1
            reason_parts = ', '.join(f"{k}:{v}" for k, v in sorted(reason_counter.items()))
            print(f"[TrackingHelper] Distanz fehlend für {len(missing)} Marker (Gruende: {reason_parts})")
    except Exception:  # noqa: BLE001
        pass

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'per_pass': per_pass,
        'pattern_size': pattern_size,
        'search_size': search_size,
        'marker_logs': marker_logs,
        'distance_stats': distance_stats,
        'per_pass_distance_stats': per_pass_stats,
        'zero_distance_count': zero_count,
        'positive_distance_count': positive_count,
        'min_positive_distance': min_positive,
        'zero_distance_ratio': zero_ratio,
    }
