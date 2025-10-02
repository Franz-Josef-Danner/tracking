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
    min_distance=100,  # NEU: Standard-Abstand fuer Duplikat-/Detect-Steuerung
):
    """
    Mehrfaches Feature-Detect (Multi-Threshold) mit Band-Überwachung (ef->za) und
    vereinheitlichter Duplikatlogik.

    WICHTIG: Duplikatprüfung verwendet ab jetzt IMMER min_distance als Distanzgrenze.
             (Parameter duplicate_tolerance_px & jede Cluster-Funktion wurden entfernt.)

    Parameter:
        start_threshold (float)   – Start Threshold.
        min_threshold (float)     – Abbruchschwelle für Threshold-Kaskade.
        factor (float)            – Multiplikator pro Pass (current *= factor).
        max_passes (int)          – Sicherheitslimit.
        remove_duplicates (bool)  – Am Ende (oder sofort bei immediate_delete) doppelte Marker löschen.
        keep_first_marker (bool)  – Ersten jemals gefundenen Marker nie als Duplikat löschen.
        immediate_delete (bool)   – Duplikate sofort beim Entstehen löschen.
    min_distance (int/float)  – (Default 100) Wird an bpy.ops.clip.detect_features übergeben UND als Duplikatgrenze genutzt.

    Rückgabe enthält u.a.:
        marker_control  – Band-Telemetrie je Pass.
        removed_duplicate_tracks / removed_duplicate_count
        per_pass, per_pass_new_counts, distance_stats, etc.
    """
    marker_control = []

    area = find_clip_editor_area(context)
    if area is None:
        return {'success': False, 'message': 'Kein Movie Clip Editor Bereich gefunden.', 'passes': 0,
                'total_added': -1, 'per_pass': [], 'marker_control': marker_control}
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return {'success': False, 'message': 'Keine gültige WINDOW Region.', 'passes': 0,
                'total_added': -1, 'per_pass': [], 'marker_control': marker_control}

    clip = get_clip_from_area(area)
    pattern_size = search_size = old_pattern = old_search = settings = None
    w = h = None
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
        except Exception:
            pass

    tracks_before = len(clip.tracking.tracks) if clip else -1

    has_threshold = False
    if bpy is not None:
        try:
            rna = bpy.ops.clip.detect_features.get_rna_type()
            has_threshold = 'threshold' in rna.properties.keys()
        except Exception:
            has_threshold = False

    per_pass = []
    passes = 0
    current = start_threshold
    marker_logs = []
    existing_track_ids = set()
    if clip and bpy is not None:
        existing_track_ids = {id(t) for t in clip.tracking.tracks}

    seen_signatures = set()
    pass_new_signatures = []

    def _build_signature(track_obj):
        try:
            marker_ref = None
            cur_frame_ctx = bpy.context.scene.frame_current if (bpy and bpy.context and bpy.context.scene) else None
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
                px = co[0] * w; py = co[1] * h
                rpx = round(px * 2) / 2.0
                rpy = round(py * 2) / 2.0
            else:
                rpx = round(co[0], 5); rpy = round(co[1], 5)
            return (getattr(track_obj, 'name', '<noname>'), marker_ref.frame, rpx, rpy)
        except Exception:
            return None

    def _ensure_tracking_mode():
        try:
            if area and hasattr(area, 'spaces'):
                space = area.spaces.active
                if getattr(space, 'mode', None) != 'TRACKING':
                    space.mode = 'TRACKING'
        except Exception:
            pass
    def apply_sizes(cur_pattern):
        if settings is None:
            return
        try:
            p = max(3, int(round(cur_pattern))); s = p * 2
            if hasattr(settings, 'default_pattern_size'): settings.default_pattern_size = p
            if hasattr(settings, 'default_search_size'): settings.default_search_size = s
            nonlocal pattern_size, search_size
            pattern_size = p; search_size = s
        except Exception:
            pass

    def run_detect(thr, allow_param=True, md=None):
        prev_count = len(clip.tracking.tracks) if (clip and bpy is not None) else 0
        note = ''
        try:
            if bpy is None:
                return 0, 'kein bpy'
            kwargs = {}
            if has_threshold and allow_param:
                kwargs['threshold'] = thr
            if md is not None:
                try:
                    kwargs['min_distance'] = int(round(md))
                except Exception:
                    kwargs['min_distance'] = int(md) if isinstance(md, (int, float)) else 0
            if kwargs:
                try:
                    bpy.ops.clip.detect_features(**kwargs)
                except TypeError as te:
                    if 'min_distance' in kwargs:
                        try:
                            k2 = dict(kwargs); k2.pop('min_distance', None)
                            bpy.ops.clip.detect_features(**k2)
                            note = f'TypeError(min_distance entfernt): {te}'
                        except Exception:
                            bpy.ops.clip.detect_features()
                            note = f'TypeError(blank): {te}'
                    else:
                        bpy.ops.clip.detect_features()
                        note = f'TypeError(blank): {te}'
            else:
                bpy.ops.clip.detect_features()
                if allow_param and not has_threshold:
                    note = 'threshold nicht unterstützt'
        except TypeError:
            if bpy is not None:
                bpy.ops.clip.detect_features()
            note = 'TypeError threshold/min_distance'
        except Exception as ex:
            note = f'Exception detect:{type(ex).__name__}'
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
        cur_frame = bpy.context.scene.frame_current if (bpy.context and bpy.context.scene) else None
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
                                    marker_ref = mm; break
                        if marker_ref is None and len(t.markers) > 0:
                            marker_ref = t.markers[0]
                        if marker_ref:
                            co_norm = marker_ref.co
                            existing_positions_px.append((co_norm[0]*w, co_norm[1]*h))
                if not existing_positions_px:
                    fallback_used = True
            except Exception:
                fallback_used = True
        count = 0

        def _safe_track_name(obj):
            try:
                nm = obj.name
                return nm if isinstance(nm, str) else str(nm)
            except Exception:
                return 'TRACK_NAME_ERR'

        for t in clip.tracking.tracks:
            if id(t) not in new_ids:
                continue
            count += 1
            marker_co_norm = None
            marker_px = None
            frame_used = None
            nearest_dist_px = None
            replaced_name = False
            removed_immediately = False
            try:
                marker = None
                if cur_frame is not None:
                    for m in t.markers:
                        if m.frame == cur_frame:
                            marker = m; break
                if marker is None and len(t.markers) > 0:
                    marker = t.markers[0]
                if marker:
                    marker_co_norm = tuple(marker.co)
                    frame_used = marker.frame
                    if w is not None and h is not None:
                        marker_px = (marker.co[0]*w, marker.co[1]*h)
                        if existing_positions_px:
                            try:
                                x, y = marker_px
                                nearest_dist_px = min(((x-ex)**2 + (y-ey)**2) for ex, ey in existing_positions_px)**0.5
                            except Exception:
                                nearest_dist_px = None
                        existing_positions_px.append(marker_px)
                if marker_logs and any(m['track_name'] == t.name for m in marker_logs):
                    replaced_name = True
            except Exception:
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

            # SOFORT-DUPLIKAT-ENTFERNUNG (min_distance als Schwelle)
            if immediate_delete and remove_duplicates:
                is_dup = False
                if nearest_dist_px is not None and nearest_dist_px <= float(min_distance):
                    is_dup = True
                elif nearest_dist_px is None and existing_positions_px:
                    is_dup = True
                if is_dup and keep_first_marker and not marker_logs:
                    is_dup = False
                if is_dup:
                    try:
                        _ensure_tracking_mode()
                        for tr in clip.tracking.tracks:
                            try: tr.select = False
                            except Exception: pass
                        try: t.select = True
                        except Exception: pass
                        try: clip.tracking.tracks.active = t  # type: ignore[attr-defined]
                        except Exception: pass
                        try:
                            _ensure_tracking_mode()
                            bpy.ops.clip.delete_track()
                            removed_immediately = True
                            marker_logs.append({
                                'pass': pass_index,
                                'threshold': thr,
                                'track_name': _safe_track_name(t),
                                'frame': frame_used,
                                'pos_norm': marker_co_norm,
                                'pos_px': marker_px,
                                'nearest_dist_px': nearest_dist_px,
                                'pattern': pattern_size,
                                'search': search_size,
                                'distance_fallback': fallback_used,
                                'replaced_name': replaced_name,
                                'no_distance_reason': no_distance_reason,
                                'removed_immediately': True,
                            })
                            continue
                        except Exception:
                            removed_immediately = False
                    except Exception:
                        removed_immediately = False

            marker_logs.append({
                'pass': pass_index,
                'threshold': thr,
                'track_name': _safe_track_name(t),
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

    MAX_RETRIES_PER_THRESHOLD = 3  # NEU: maximale Wiederholungen eines Thresholds, wenn ausserhalb Band

    try:
        try:
            if bpy is None:
                raise RuntimeError('bpy nicht verfuegbar')
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    # (Unverändert – Ein-Pass Modus)
                    apply_sizes(pattern_size)
                    added, note = run_detect(current, allow_param=False, md=min_distance)
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
                    note_ctl = _apply_marker_control_and_maybe_modify(
                        note=None,
                        new_sigs=new_sigs_this_pass,
                        passes_ref=1,
                        threshold=current,
                        marker_control=marker_control
                    )
                    if note_ctl:
                        note = (note + ' | ' + note_ctl) if note else note_ctl
                    per_pass.append((current, added, note or 'kein threshold Param'))
                    passes = 1
                else:
                    cur_pattern_progressive = float(pattern_size) if pattern_size else None
                    while current >= min_threshold and passes < max_passes:
                        if cur_pattern_progressive is not None:
                            apply_sizes(cur_pattern_progressive)

                        retry = 0
                        # Diese Schleife wiederholt denselben Threshold, wenn ausserhalb Band
                        while True:
                            # Snapshot vor Detect
                            pre_track_names = set()
                            if clip and bpy is not None:
                                pre_track_names = {t.name for t in clip.tracking.tracks}

                            # Logging mit neuem Pass-Index (added/note bereits gesetzt)
                            pass_index = passes + 1
                            log_new_tracks(pass_index, current)

                            # Neue Signaturen für diesen Versuch
                            new_sigs_this_attempt = []
                            if clip:
                                for t in clip.tracking.tracks:
                                    sig = _build_signature(t)
                                    if sig and sig not in seen_signatures and sig not in new_sigs_this_attempt:
                                        new_sigs_this_attempt.append(sig)
                            for sig in new_sigs_this_attempt:
                                seen_signatures.add(sig)
                            pass_new_signatures.append(new_sigs_this_attempt)

                            # Control
                            ctl_note = _apply_marker_control_and_maybe_modify(
                                note=note,
                                new_sigs=new_sigs_this_attempt,
                                passes_ref=pass_index,
                                threshold=current,
                                marker_control=marker_control
                            )
                            if ctl_note:
                                note = (note + ' | ' + ctl_note) if note else ctl_note

                            # Werte aus marker_control
                            mc_last = marker_control[-1] if marker_control else {}
                            in_band = mc_last.get('in_band', False)
                            am = mc_last.get('am', 0)
                            ug = mc_last.get('ug', 0.0)
                            og = mc_last.get('og', 0.0)

                            # Protokollierung dieses Versuchs
                            per_pass.append((current, added, note))
                            passes += 1

                            # Abbruchbedingungen Versuchsschleife:
                            if in_band or retry >= MAX_RETRIES_PER_THRESHOLD or passes >= max_passes:
                                break

                            # Außerhalb Band -> Wiederholung:
                            # 1) Neu hinzugekommene Tracks (dieses Versuches) ermitteln
                            if clip and bpy is not None:
                                post_track_names = {t.name for t in clip.tracking.tracks}
                                new_names_this_try = list(post_track_names - pre_track_names)

                                if new_names_this_try:
                                    # 2) Löschen dieser neuen Tracks
                                    def _delete_names(name_list):
                                        removed_local = 0
                                        for nm in name_list:
                                            trk = next((t for t in clip.tracking.tracks if t.name == nm), None)
                                            if not trk:
                                                continue
                                            try:
                                                for tr in clip.tracking.tracks:
                                                    try:
                                                        tr.select = False
                                                    except Exception:
                                                        pass
                                                try:
                                                    trk.select = True
                                                except Exception:
                                                    pass
                                                try:
                                                    clip.tracking.tracks.active = trk  # type: ignore[attr-defined]
                                                except Exception:
                                                    pass
                                                _ensure_tracking_mode()
                                                try:
                                                    bpy.ops.clip.delete_track()
                                                except TypeError:
                                                    bpy.ops.clip.delete_track()
                                                if not any(t.name == nm for t in clip.tracking.tracks):
                                                    removed_local += 1
                                            except Exception:
                                                pass
                                        return removed_local
                                    try:
                                        with context.temp_override(area=area, region=region):
                                            _delete_names(new_names_this_try)
                                    except Exception:
                                        _delete_names(new_names_this_try)
                            # 3) Retry-Zähler erhöhen und erneut denselben Threshold versuchen
                            retry += 1
                            continue  # zurück in while True

                        # Nächster Threshold
                        current *= factor
                        if cur_pattern_progressive is not None:
                            cur_pattern_progressive *= 1.15
                        # Schleifenende wenn nächste Stufe unter min_threshold
        except AttributeError:
            # Fallback unverändert (keine Wiederholungen implementiert)
            override = context.copy()
            override['area'] = area
            override['region'] = region
            # (Optional könntest du hier die gleiche Retry-Logik nachziehen.)
            if not has_threshold:
                apply_sizes(pattern_size)
                added, note = run_detect(current, allow_param=False, md=min_distance)
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
                        added, note = run_detect(current, allow_param=True, md=min_distance)
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
                    except Exception:
                        per_pass.append((current, 0, 'fallback Fehler'))
                        break
                    passes += 1
                    current *= factor
                    if cur_pattern_progressive is not None:
                        cur_pattern_progressive *= 1.5

        # Sammel-Duplikat-Entfernung (nur wenn nicht immediate_delete)
        removed_track_names = set()
        if remove_duplicates and clip and bpy is not None and not immediate_delete:
            # Kandidaten: Abstand <= min_distance oder dist None
            candidates = []
            for m in marker_logs:
                dist = m.get('nearest_dist_px')
                name = m['track_name']
                if keep_first_marker and m is marker_logs[0]:
                    continue
                if dist is None:
                    candidates.append(name)
                elif dist <= float(min_distance):
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
                                try: tr.select = False
                                except Exception: pass
                            try: trk.select = True
                            except Exception: pass
                            try: clip.tracking.tracks.active = trk  # type: ignore[attr-defined]
                            except Exception: pass
                            try:
                                _ensure_tracking_mode()
                                bpy.ops.clip.delete_track()
                            except TypeError:
                                bpy.ops.clip.delete_track()
                            if not any(t.name == nm for t in clip.tracking.tracks):
                                removed_local.append(nm)
                        except Exception:
                            pass
                    return removed_local
                try:
                    with context.temp_override(area=area, region=region):
                        removed_list = _delete_list(candidates)
                except Exception:
                    removed_list = _delete_list(candidates)
                removed_track_names.update(removed_list)

    except Exception as e:
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
            except Exception:
                pass

    if clip:
        total_added = len(clip.tracking.tracks) - tracks_before
    else:
        total_added = -1

    def _compute_stats(values):
        if not values:
            return {'count': 0, 'min': None, 'max': None, 'mean': None, 'median': None}
        s = sorted(values); n = len(s)
        mean = sum(s)/n
        median = s[n//2] if n % 2 else 0.5*(s[n//2 - 1] + s[n//2])
        return {'count': n, 'min': s[0], 'max': s[-1], 'mean': mean, 'median': median}

    removed_for_stats = set()
    if 'removed_track_names' in locals():
        removed_for_stats.update(removed_track_names)

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
    except Exception:
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
        'per_pass_new_counts': per_pass_new_counts,
        'marker_control': marker_control,
        'min_distance': min_distance,
        'duplicate_distance_used': float(min_distance),  # explizit ausgewiesen
    }

# _apply_marker_control_and_maybe_modify bleibt unverändert darunter, falls weiter genutzt.
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
