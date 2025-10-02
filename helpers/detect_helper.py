try:  # Blender Umgebung
    import bpy  # type: ignore
except ImportError:  # außerhalb Blender
    bpy = None  # type: ignore

import traceback

# Minimal-Logging Modus: Nur noch pro Detect-Pass die Markeranzahl ausgeben.
# Fuer Debugging kann VERBOSE_TRACKING_LOGS=True gesetzt werden.
VERBOSE_TRACKING_LOGS = False

def _vprint(*args, **kwargs):  # noqa: D401
    """Interne Helferfunktion fuer optionale (Verbose) Ausgaben."""
    if VERBOSE_TRACKING_LOGS:
        print(*args, **kwargs)


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


def detect_features_multipass(
    context,
    start_threshold=1.0,
    min_threshold=0.1,   # vorher 0.0001
    factor=0.5,
    max_passes=32,
    remove_duplicates=True,
    duplicate_tolerance_px=0.0,
    keep_first_marker=True,
    immediate_delete=False,
    cluster_consolidate=False,
    cluster_tolerance_px=2.0,
    cluster_max_per_cluster=1,
):
    """Fuehrt mehrfache Feature-Erkennung aus (Multi-Threshold) und steuert optional über scene.marker_per_frame.

    Rückgabe enthält Diagnose- und Kontroll-Daten (marker_control) mit Feldern:
        pass, ef, za, ug, og, am, in_band, factor, stopped, reason
    """
    # Sicherstellen: marker_control immer vorhanden
    marker_control = []

    area = find_clip_editor_area(context)
    if area is None:
        return {
            'success': False,
            'message': 'Kein Movie Clip Editor Bereich gefunden (oeffne einen Clip Editor).',
            'passes': 0,
            'total_added': -1,
            'per_pass': [],
            'marker_control': marker_control,
        }
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return {
            'success': False,
            'message': 'Keine gueltige WINDOW Region im Clip Editor gefunden.',
            'passes': 0,
            'total_added': -1,
            'per_pass': [],
            'marker_control': marker_control,
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
            pattern_size = max(3, int(round(w * 0.01)))
            search_size = pattern_size * 2
            settings = getattr(clip.tracking, 'settings', None)
            if settings is not None:
                old_pattern = getattr(settings, 'default_pattern_size', None)
                old_search = getattr(settings, 'default_search_size', None)
                if hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = pattern_size
                if hasattr(settings, 'default_search_size'):
                    settings.default_search_size = search_size
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

    # Sanitisierung eingehender Parameter
    try:
        duplicate_tolerance_px = float(duplicate_tolerance_px)
    except Exception:  # noqa: BLE001
        duplicate_tolerance_px = 0.0
    try:
        cluster_tolerance_px = float(cluster_tolerance_px)
    except Exception:  # noqa: BLE001
        cluster_tolerance_px = 2.0
    try:
        cluster_max_per_cluster = int(cluster_max_per_cluster)
    except Exception:  # noqa: BLE001
        cluster_max_per_cluster = 1

    per_pass = []
    passes = 0
    current = start_threshold
    marker_logs = []
    existing_track_ids = set()
    if clip and bpy is not None:
        existing_track_ids = {id(t) for t in clip.tracking.tracks}

    seen_signatures = set()
    pass_new_signatures = []
    per_pass_new_counts_internal = []

    def _build_signature(track_obj):
        try:
            marker_ref = None
            cur_frame_ctx = bpy.context.scene.frame_current if bpy and bpy.context and bpy.context.scene else None
            if cur_frame_ctx is not None:
                for mm in track_obj.markers:
                    if mm.frame == cur_frame_ctx:
                        marker_ref = mm
                        break
            if marker_ref is None and len(track_obj.markers) > 0:
                marker_ref = track_obj.markers[0]
            if marker_ref is None:
                return None
            co = marker_ref.co
            if w is not None and h is not None:
                px = co[0] * w
                py = co[1] * h
                rpx = round(px * 2) / 2.0
                rpy = round(py * 2) / 2.0
            else:
                rpx = round(co[0], 5)
                rpy = round(co[1], 5)
            frame_val = marker_ref.frame
            name_val = getattr(track_obj, 'name', '<noname>')
            return (name_val, frame_val, rpx, rpy)
        except Exception:  # noqa: BLE001
            return None

    def _ensure_tracking_mode():
        try:
            if area and hasattr(area, 'spaces') and area.spaces:
                space = area.spaces.active
                if hasattr(space, 'mode') and getattr(space, 'mode', None) != 'TRACKING':
                    space.mode = 'TRACKING'
        except Exception:  # noqa: BLE001
            pass

    def apply_sizes(cur_pattern):
        if settings is None:
            return
        try:
            p = max(3, int(round(cur_pattern)))
            s = p * 2
            if hasattr(settings, 'default_pattern_size'):
                settings.default_pattern_size = p
            if hasattr(settings, 'default_search_size'):
                settings.default_search_size = s
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
                return 0, 'kein bpy'
            if has_threshold and allow_param:
                bpy.ops.clip.detect_features(threshold=thr)
            else:
                bpy.ops.clip.detect_features()
                if allow_param and not has_threshold:
                    note = 'threshold nicht unterstuetzt'
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
        existing_positions_px = []
        fallback_used = False
        if w is not None and h is not None:
            try:
                if marker_logs:
                    existing_positions_px.extend([m['pos_px'] for m in marker_logs if m.get('pos_px')])
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
                if not existing_positions_px:
                    fallback_used = True
            except Exception:  # noqa: BLE001
                fallback_used = True
        count = 0

        def _safe_track_name(obj):
            try:
                nm = obj.name
                return nm if isinstance(nm, str) else str(nm)
            except UnicodeDecodeError as ue:
                raw = getattr(obj, 'name', b'?')
                if isinstance(raw, bytes):
                    try:
                        return 'TRACK_NAME_ERR:' + raw.decode('utf-8', 'backslashreplace')
                    except Exception:  # noqa: BLE001
                        pass
                return f'TRACK_NAME_ERR:{ue}'
            except Exception:  # noqa: BLE001
                return 'TRACK_NAME_ERR:unknown'

        for t in clip.tracking.tracks:
            if id(t) in new_ids:
                count += 1
                marker_co_norm = None
                marker_px = None
                frame_used = None
                nearest_dist_px = None
                replaced_name = False
                removed_immediately = False
                safe_name = _safe_track_name(t)
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
                            if existing_positions_px:
                                try:
                                    x, y = marker_px
                                    nearest_dist_px = min(
                                        ((x - ex) ** 2 + (y - ey) ** 2) for ex, ey in existing_positions_px
                                    ) ** 0.5
                                except Exception:  # noqa: BLE001
                                    nearest_dist_px = None
                            existing_positions_px.append(marker_px)
                    if marker_logs and any(m['track_name'] == t.name for m in marker_logs):
                        replaced_name = True
                except Exception:  # noqa: BLE001
                    pass

                no_distance_reason = None
                if nearest_dist_px is None:
                    if marker_px is None:
                        no_distance_reason = 'no_marker_position'
                    elif not existing_positions_px or (
                        len(existing_positions_px) == 1 and existing_positions_px[-1] == marker_px
                    ):
                        no_distance_reason = 'no_reference_positions'
                    else:
                        no_distance_reason = 'calc_error'

                if immediate_delete and remove_duplicates:
                    is_duplicate = False
                    if nearest_dist_px is not None and nearest_dist_px <= duplicate_tolerance_px:
                        is_duplicate = True
                    elif nearest_dist_px is None and existing_positions_px:
                        is_duplicate = True
                    if is_duplicate and keep_first_marker and not marker_logs:
                        is_duplicate = False
                    if is_duplicate:
                        try:
                            _ensure_tracking_mode()
                            for tr in clip.tracking.tracks:
                                try:
                                    tr.select = False
                                except Exception:  # noqa: BLE001
                                    pass
                            try:
                                t.select = True
                            except Exception:  # noqa: BLE001
                                pass
                            try:
                                clip.tracking.tracks.active = t  # type: ignore[attr-defined]
                            except Exception:  # noqa: BLE001
                                pass
                            try:
                                _ensure_tracking_mode()
                                bpy.ops.clip.delete_track()
                                removed_immediately = True
                                continue
                            except Exception:  # noqa: BLE001
                                removed_immediately = False
                        except Exception:  # noqa: BLE001
                            removed_immediately = False

                marker_logs.append({
                    'pass': pass_index,
                    'threshold': thr,
                    'track_name': safe_name,
                    'frame': frame_used,
                    'pos_norm': marker_co_norm,
                    'pos_px': marker_px,
                    'nearest_dist_px': nearest_dist_px,
                    'pattern': pattern_size,
                    'search': search_size,
                    'distance_fallback': fallback_used,
                    'replaced_name': replaced_name,
                    'no_distance_reason': no_distance_reason,
                    'removed_immediately': removed_immediately,
                })
        existing_track_ids.update(new_ids)
        return count

    try:
        try:
            if bpy is None:
                raise RuntimeError('bpy nicht verfuegbar')
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    apply_sizes(pattern_size)
                    added, note = run_detect(current, allow_param=False)
                    log_new_tracks(1, current)
                    new_sigs_this_pass = []
                    if clip:
                        for t in clip.tracking.tracks:
                            sig = _build_signature(t)
                            if sig and sig not in seen_signatures and sig not in new_sigs_this_pass:
                                new_sigs_this_pass.append(sig)
                    for sig in new_sigs_this_pass:
                        seen_signatures.add(sig)
                    pass_new_signatures.append(new_sigs_this_pass)

                    # Steuerlogik Ein-Pass
                    note = _apply_marker_control_and_maybe_modify(note=None,  # Placeholder (kein Loop)
                                                                  new_sigs=new_sigs_this_pass,
                                                                  passes_ref=1,
                                                                  threshold=current,
                                                                  marker_control=marker_control) or note
                    per_pass.append((current, added, note or 'kein threshold Param'))
                    passes = 1
                else:
                    cur_pattern_progressive = float(pattern_size) if pattern_size else None
                    stop_detect_loop = False
                    while current >= min_threshold and passes < max_passes:
                        if cur_pattern_progressive is not None:
                            apply_sizes(cur_pattern_progressive)
                        added, note = run_detect(current, allow_param=True)
                        log_new_tracks(passes + 1, current)
                        new_sigs_this_pass = []
                        if clip:
                            for t in clip.tracking.tracks:
                                sig = _build_signature(t)
                                if sig and sig not in seen_signatures and sig not in new_sigs_this_pass:
                                    new_sigs_this_pass.append(sig)
                        for sig in new_sigs_this_pass:
                            seen_signatures.add(sig)
                        pass_new_signatures.append(new_sigs_this_pass)

                        ctl_note = _apply_marker_control_and_maybe_modify(
                            note=note,
                            new_sigs=new_sigs_this_pass,
                            passes_ref=passes + 1,
                            threshold=current,
                            marker_control=marker_control
                        )
                        if ctl_note:
                            note = (note + ' | ' + ctl_note) if note else ctl_note

                        per_pass.append((current, added, note))
                        passes += 1
                        current *= factor
                        if cur_pattern_progressive is not None:
                            cur_pattern_progressive *= 1.15
        except AttributeError:
            # Fallback ohne temp_override (Minimalvariante—Steuerlogik kann hier bei Bedarf nachgezogen werden)
            override = context.copy()
            override['area'] = area
            override['region'] = region
            if not has_threshold:
                apply_sizes(pattern_size)
                added, note = run_detect(current, allow_param=False)
                log_new_tracks(1, current)
                new_sigs_this_pass = []
                if clip:
                    for t in clip.tracking.tracks:
                        sig = _build_signature(t)
                        if sig and sig not in seen_signatures and sig not in new_sigs_this_pass:
                            new_sigs_this_pass.append(sig)
                for sig in new_sigs_this_pass:
                    seen_signatures.add(sig)
                pass_new_signatures.append(new_sigs_this_pass)
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
                        new_sigs_this_pass = []
                        if clip:
                            for t in clip.tracking.tracks:
                                sig = _build_signature(t)
                                if sig and sig not in seen_signatures and sig not in new_sigs_this_pass:
                                    new_sigs_this_pass.append(sig)
                        for sig in new_sigs_this_pass:
                            seen_signatures.add(sig)
                        pass_new_signatures.append(new_sigs_this_pass)
                        per_pass.append((current, added, note or 'fallback'))
                    except Exception:  # noqa: BLE001
                        per_pass.append((current, 0, 'fallback Fehler'))
                        break
                    passes += 1
                    current *= factor
                    if cur_pattern_progressive is not None:
                        cur_pattern_progressive *= 1.5

        # (Rest des Originals: Duplikat-Entfernung, Cluster-Konsolidierung, Statistiken etc.)
        removed_track_names = set()
        if remove_duplicates and clip and bpy is not None and not immediate_delete:
            candidates = []
            for m in marker_logs:
                dist = m.get('nearest_dist_px')
                name = m['track_name']
                if keep_first_marker and m is marker_logs[0]:
                    continue
                if dist is None:
                    candidates.append(name)
                elif dist <= duplicate_tolerance_px:
                    candidates.append(name)

            if candidates:
                def _delete_list(name_list):
                    removed_local = []
                    for nm in name_list:
                        trk = next((t for t in clip.tracking.tracks if t.name == nm), None)
                        if not trk:
                            continue
                        try:
                            _ensure_tracking_mode()
                            for tr in clip.tracking.tracks:
                                try:
                                    tr.select = False
                                except Exception:  # noqa: BLE001
                                    pass
                            try:
                                trk.select = True
                            except Exception:  # noqa: BLE001
                                pass
                            try:
                                clip.tracking.tracks.active = trk  # type: ignore[attr-defined]
                            except Exception:  # noqa: BLE001
                                pass
                            try:
                                _ensure_tracking_mode()
                                bpy.ops.clip.delete_track()
                            except TypeError:
                                bpy.ops.clip.delete_track()
                            if not any(t.name == nm for t in clip.tracking.tracks):
                                removed_local.append(nm)
                        except Exception:  # noqa: BLE001
                            pass
                    return removed_local
                try:
                    with context.temp_override(area=area, region=region):
                        removed_list = _delete_list(candidates)
                except Exception:
                    removed_list = _delete_list(candidates)
                removed_track_names.update(removed_list)

        cluster_removed = []
        cluster_info = None
        if cluster_consolidate and clip and bpy is not None:
            try:
                name_order = {m['track_name']: i for i, m in enumerate(marker_logs)}
                track_positions = []
                if w is not None and h is not None:
                    for t in clip.tracking.tracks:
                        marker_ref = None
                        cur_frame = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
                        if cur_frame is not None:
                            for mm in t.markers:
                                if mm.frame == cur_frame:
                                    marker_ref = mm
                                    break
                        if marker_ref is None and len(t.markers) > 0:
                            marker_ref = t.markers[0]
                        if marker_ref is None:
                            continue
                        co_norm = marker_ref.co
                        track_positions.append(
                            (t.name, name_order.get(t.name, 10**9), co_norm[0] * w, co_norm[1] * h)
                        )
                track_positions.sort(key=lambda x: (x[1], x[0]))
                tol2 = float(cluster_tolerance_px) ** 2
                clusters = []
                for nm, _, px, py in track_positions:
                    assigned = False
                    for c in clusters:
                        cx, cy = c['center']
                        if (px - cx) ** 2 + (py - cy) ** 2 <= tol2:
                            c['members'].append((nm, px, py))
                            assigned = True
                            break
                    if not assigned:
                        clusters.append({'center': (px, py), 'members': [(nm, px, py)]})
                to_remove_cluster = []
                for c in clusters:
                    members = c['members']
                    if len(members) > cluster_max_per_cluster:
                        surplus = members[cluster_max_per_cluster:]
                        to_remove_cluster.extend(n for (n, _, _) in surplus)
                if to_remove_cluster:
                    def _delete_names(name_list):
                        removed_local = []
                        for nm in name_list:
                            trk = next((t for t in clip.tracking.tracks if t.name == nm), None)
                            if not trk:
                                continue
                            try:
                                _ensure_tracking_mode()
                                for tr in clip.tracking.tracks:
                                    try:
                                        tr.select = False
                                    except Exception:  # noqa: BLE001
                                        pass
                                try:
                                    trk.select = True
                                except Exception:  # noqa: BLE001
                                    pass
                                try:
                                    clip.tracking.tracks.active = trk  # type: ignore[attr-defined]
                                except Exception:  # noqa: BLE001
                                    pass
                                try:
                                    _ensure_tracking_mode()
                                    bpy.ops.clip.delete_track()
                                except TypeError:
                                    bpy.ops.clip.delete_track()
                                if not any(t.name == nm for t in clip.tracking.tracks):
                                    removed_local.append(nm)
                            except Exception:  # noqa: BLE001
                                pass
                        return removed_local
                    try:
                        with context.temp_override(area=area, region=region):
                            removed_cluster = _delete_names(to_remove_cluster)
                    except Exception:
                        removed_cluster = _delete_names(to_remove_cluster)
                    cluster_removed.extend(removed_cluster)
                cluster_info = {
                    'clusters_total': len(clusters),
                    'clusters_gt1': sum(1 for c in clusters if len(c['members']) > 1),
                    'removed_in_cluster': len(cluster_removed),
                    'tolerance_px': cluster_tolerance_px,
                    'max_per_cluster': cluster_max_per_cluster,
                }
            except Exception:  # noqa: BLE001
                pass

    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc()
        return {
            'success': False,
            'message': f'Fehler: {e}',
            'exception_type': type(e).__name__,
            'traceback': tb,
            'passes': passes,
            'total_added': -1,
            'per_pass': per_pass,
            'pattern_size': pattern_size,
            'search_size': search_size,
            'marker_logs': marker_logs,
            'marker_control': marker_control,
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

    if clip:
        total_added = len(clip.tracking.tracks) - tracks_before
    else:
        total_added = -1

    def _compute_stats(values):
        if not values:
            return {'count': 0, 'min': None, 'max': None, 'mean': None, 'median': None}
        s = sorted(values)
        n = len(s)
        mean = sum(s) / n
        median = s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
        return {'count': n, 'min': s[0], 'max': s[-1], 'mean': mean, 'median': median}

    removed_for_stats = set()
    if 'removed_track_names' in locals():
        removed_for_stats.update(removed_track_names)
    if 'cluster_removed' in locals():
        removed_for_stats.update(cluster_removed)

    distances_all = [
        m['nearest_dist_px'] for m in marker_logs
        if m.get('nearest_dist_px') is not None and m['track_name'] not in removed_for_stats
    ]
    distance_stats = _compute_stats(distances_all)
    distances_per_pass = {}
    for m in marker_logs:
        if m.get('nearest_dist_px') is None or m['track_name'] in removed_for_stats:
            continue
        p = m['pass']
        distances_per_pass.setdefault(p, []).append(m['nearest_dist_px'])
    per_pass_stats = {p: _compute_stats(vals) for p, vals in distances_per_pass.items()}

    zero_count = sum(1 for d in distances_all if d == 0.0)
    positive_distances = [d for d in distances_all if d and d > 0.0]
    min_positive = min(positive_distances) if positive_distances else None
    positive_count = len(positive_distances)
    zero_ratio = (zero_count / len(distances_all)) if distances_all else None

    # Überlebende Signaturen zählen (nach evtl. Löschungen)
    surviving_signatures = set()
    if clip:
        for t in clip.tracking.tracks:
            sig = _build_signature(t)
            if sig:
                surviving_signatures.add(sig)
    final_counts = []
    for sig_list in pass_new_signatures:
        cnt = sum(1 for sig in sig_list if sig in surviving_signatures)
        final_counts.append(cnt)
    per_pass_new_counts = final_counts

    try:
        for idx, cnt in enumerate(per_pass_new_counts, start=1):
            print(f"[Detect] Pass {idx} Marker={cnt}")
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
        'removed_duplicate_tracks': sorted(removed_track_names) if 'removed_track_names' in locals() else [],
        'removed_duplicate_count': len(removed_track_names) if 'removed_track_names' in locals() else 0,
        'cluster_removed_tracks': sorted(cluster_removed) if 'cluster_removed' in locals() else [],
        'cluster_removed_count': len(cluster_removed) if 'cluster_removed' in locals() else 0,
        'cluster_stats': cluster_info,
        'per_pass_new_counts': per_pass_new_counts,
        'marker_control': marker_control,
    }


def _apply_marker_control_and_maybe_modify(note, new_sigs, passes_ref, threshold, marker_control):
    """Marker-Band-Logik (rein beobachtend, kein Stopp).

    Fügt einen Datensatz in marker_control ein:
        pass, threshold, ef, za, ug, og, am, deviation, factor, in_band, reason, stopped(False)

    Rückgabe: kurzer Note-String (ctl:band | ctl:dev factor=... | ctl:zero za=0 | ctl:empty am=0)
    """
    try:
        scene = bpy.context.scene if bpy and bpy.context else None
        if not scene or not hasattr(scene, 'marker_per_frame'):
            return None

        ef = max(0, int(scene.marker_per_frame))
        za = (ef * 4.0) / 14.0 if ef > 0 else 0.0
        ug = za * 0.9
        og = za * 1.1
        am = len(new_sigs)

        if za <= 0:
            factor_val = None
            deviation = None
            in_band = False
            reason = 'za=0'
            note_out = 'ctl:zero za=0'
        else:
            deviation = ((am - za) / za) if za > 0 else None
            in_band = (am > ug) and (am < og)
            if am <= 0:
                factor_val = 0.0
                reason = 'am=0'
                note_out = 'ctl:empty am=0'
            elif in_band:
                factor_val = None
                reason = 'band'
                note_out = 'ctl:band'
            else:
                # md / (za / am) == md * am / za
                md = 100.0
                factor_val = md * am / za
                reason = 'out_of_band'
                note_out = f'ctl:dev factor={factor_val:.2f}'

        marker_control.append({
            'pass': passes_ref,
            'threshold': threshold,
            'ef': ef,
            'za': za,
            'ug': ug,
            'og': og,
            'am': am,
            'deviation': deviation,          # relativer Fehler (am-za)/za
            'factor': factor_val,            # Skalierungsfaktor-Idee
            'in_band': in_band,
            'reason': reason,
            'stopped': False,                # bleibt für Kompatibilität
        })
        return note_out
    except Exception as _err:  # noqa: BLE001
        return f'ctl:error {type(_err).__name__}'
