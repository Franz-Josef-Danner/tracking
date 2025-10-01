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
    min_threshold=0.0001,
    factor=0.5,
    max_passes=32,
    remove_duplicates=True,
    duplicate_tolerance_px=0.0,
    keep_first_marker=True,
    immediate_delete=False,
    cluster_consolidate=False,
    cluster_tolerance_px=2.0,
    cluster_max_per_cluster=1,
    min_new_markers_per_pass=None,
    dynamic_min_distance_px=100.0,
    target_range_lower=None,
    target_range_upper=None,
):
    """Fuehrt mehrfache Feature-Erkennung aus.

    Returns:
        dict mit Schluesseln:
            success (bool)
            message (str)
            passes (int)
            total_added (int | -1)
        per_pass (list[tuple(threshold, added, note)])
            removed_duplicate_tracks (list[str])
            removed_duplicate_count (int)
        cluster_removed_tracks (list[str])
        cluster_removed_count (int)
        cluster_stats (dict | None)
    """
    area = find_clip_editor_area(context)
    if area is None:
        return {
            'success': False,
            'message': 'Kein Movie Clip Editor Bereich gefunden (oeffne einen Clip Editor).'
        }
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return {
            'success': False,
            'message': 'Keine gueltige WINDOW Region im Clip Editor gefunden.'
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
            _vprint(f"[TrackingHelper] Clip Breite (px): {w}")
            # Berechnung gemoaß Anforderung:
            # pattern_size = horizontale Aufloesung * 0.01
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
                _vprint(f"[TrackingHelper] Set pattern_size={pattern_size}, search_size={search_size}")
        except Exception:  # noqa: BLE001
            pass
    tracks_before = len(clip.tracking.tracks) if clip else -1

    # Pruefen ob threshold unterstuetzt wird
    has_threshold = False
    if bpy is not None:
        try:
            rna = bpy.ops.clip.detect_features.get_rna_type()
            has_threshold = 'threshold' in rna.properties.keys()
        except Exception:  # noqa: BLE001
            has_threshold = False

    # Sichere Konvertierung der moeglicherweise als Property uebergebenen Werte
    aborted_due_to_min = False
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
    marker_logs = []  # speichert detailinformationen neuer Marker
    existing_track_ids = set()
    if clip and bpy is not None:
        existing_track_ids = {id(t) for t in clip.tracking.tracks}

    # Signatur-basierte Nachverfolgung aller jemals gesehenen Marker (Name, Frame, Position in Pixeln gerundet)
    seen_signatures = set()
    pass_new_signatures = []  # Liste von Listen: neu erkannte Signaturen pro Pass (vor spaeterem Entfernen)
    per_pass_new_counts_internal = []  # finale Zahlen (erst nach Entfernen berechnet)

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
                # Rundung auf 0.5 Pixel zur Stabilisierung gegen minimalen Jitter
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
        """Versucht den Clip Editor in den TRACKING Modus zu versetzen, falls moeglich."""
        try:
            if area and hasattr(area, 'spaces') and area.spaces:
                space = area.spaces.active
                # Manche Versionen haben space.mode fuer ClipEditor
                if hasattr(space, 'mode'):
                    # Nur setzen wenn nicht schon richtig
                    if getattr(space, 'mode', None) != 'TRACKING':
                        space.mode = 'TRACKING'
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
            # fuer Rueckgabe aktualisieren (letzte Werte)
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
        # NEU: Wir verwenden primoar alle zuvor geloggten Marker-Positionen (marker_logs),
        # damit auch bei Blender-Replacements (IDs oandern sich) die Distanz-Basis erhalten bleibt.
        # Zusoatzlich sammeln wir – falls verfuegbar – die realen existierenden Track-Objekt-Positionen.
        existing_positions_px = []  # inkrementell erweitert, auch innerhalb dieses Passes
        fallback_used = False
        if w is not None and h is not None:
            try:
                # Basis aus allen zuvor geloggten Markern (Pass < aktueller Pass)
                if marker_logs:
                    existing_positions_px.extend([m['pos_px'] for m in marker_logs if m.get('pos_px')])
                # Ergoanzend: aktuelle Track-Objekte, die nicht neu sind (sofern Blender sie nicht ersetzt hat)
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
                # Falls immer noch leer (kein einziger frueherer Marker), bekommen die ersten neuen Marker keine Distanz.
                if not existing_positions_px:
                    fallback_used = True  # markiere nur zur Info
            except Exception:  # noqa: BLE001
                fallback_used = True
        count = 0
        # Helper einmal definieren (nicht pro Track neu)
        def _safe_track_name(obj):
            try:
                nm = obj.name
                if isinstance(nm, str):
                    return nm
                return str(nm)
            except UnicodeDecodeError as ue:  # spezieller Fall
                raw = getattr(obj, 'name', b'?')
                try:
                    if isinstance(raw, bytes):
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
                            # Distanz zu allen vorhandenen (bisherigen) Marker-Positionen berechnen
                            if existing_positions_px:
                                try:
                                    x, y = marker_px
                                    nearest_dist_px = min(((x - ex) ** 2 + (y - ey) ** 2) for ex, ey in existing_positions_px) ** 0.5
                                except Exception:  # noqa: BLE001
                                    nearest_dist_px = None
                            # Aktuellen Marker sofort zu Basis hinzufuegen, damit spoatere Marker IN DIESEM PASS
                            # ihre Distanz auch zu ihm berechnen koennen.
                            existing_positions_px.append(marker_px)
                    # Pruefen, ob Track-Name schon frueher existierte (ersetzt / dupliziert); nur fuer Analysezwecke
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
                # Optional: sofortiges Loeschen (Default deaktiviert, weil instabil in manchen Kontexten)
                if immediate_delete and remove_duplicates:
                    is_duplicate = False
                    if nearest_dist_px is not None and nearest_dist_px <= duplicate_tolerance_px:
                        is_duplicate = True
                    elif nearest_dist_px is None and existing_positions_px:  # nur wenn Referenz existiert
                        is_duplicate = True
                    # keep_first_marker schuetzt den allerersten Marker komplett
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
                                _vprint(
                                    f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} DUPLIKAT ENTFERNT '{t.name}' dist={nearest_dist_px} (immediate)"
                                )
                                continue
                            except Exception:  # noqa: BLE001
                                removed_immediately = False
                        except Exception:  # noqa: BLE001
                            removed_immediately = False
                try:
                    _vprint(
                        f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} NEUER TRACK '{safe_name}' "
                        f"frame={frame_used} pos_norm={marker_co_norm} pos_px={marker_px} nearest_px={nearest_dist_px} pattern={pattern_size} search={search_size}"
                    )
                except UnicodeDecodeError as ue_print:  # should not happen now
                    _vprint(f"[TrackingHelper][WARN] Unicode problem beim Drucken eines Track-Namens: {ue_print}")
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
            # Prefer temp_override
            if bpy is None:
                raise RuntimeError('bpy nicht verfuegbar')
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    # Set sizes fuer diesen Pass
                    apply_sizes(pattern_size)
                    # Vorher bekannte Signaturen merken
                    before_known = set(seen_signatures)
                    added, note = run_detect(current, allow_param=False)
                    log_new_tracks(passes + 1, current)
                    new_sigs_this_pass = []
                    if clip:
                        for t in clip.tracking.tracks:
                            sig = _build_signature(t)
                            if sig and sig not in seen_signatures and sig not in new_sigs_this_pass:
                                new_sigs_this_pass.append(sig)
                    # jetzt neue in globale Menge aufnehmen (fuer folgende Paesse nicht nochmal neu)
                    for sig in new_sigs_this_pass:
                        seen_signatures.add(sig)
                    pass_new_signatures.append(new_sigs_this_pass)
                    per_pass.append((current, added, note or 'kein threshold Param'))
                    passes = 1
                else:
                    cur_pattern_progressive = float(pattern_size) if pattern_size else None
                    while current >= min_threshold and passes < max_passes:
                        if cur_pattern_progressive is not None:
                            apply_sizes(cur_pattern_progressive)
                        target_cnt = min_new_markers_per_pass
                        # Falls ein expliziter Range uebergeben wurde, verwende diesen; sonst exakt target_cnt
                        if target_range_lower is not None or target_range_upper is not None:
                            range_lo = target_range_lower if target_range_lower is not None else target_cnt
                            range_hi = target_range_upper if target_range_upper is not None else target_cnt
                        else:
                            range_lo = target_cnt
                            range_hi = target_cnt
                        # Starte jede Pass-Runde mit Basis-Mindestdistanz 100 (oder dynamic_min_distance_px falls gesetzt)
                        base_md = float(dynamic_min_distance_px) if dynamic_min_distance_px else 100.0
                        md = base_md
                        max_attempts = 15
                        attempt = 1
                        accepted = False
                        best_attempt_diff = None
                        best_attempt_data = None
                        # Menge akzeptierter Signaturen aus vorigen Paessen (bereits in seen_signatures)
                        while attempt <= max_attempts and not accepted:
                            # Snapshot vor Detect
                            pre_tracks = set(id(t) for t in clip.tracking.tracks) if (clip and bpy is not None) else set()
                            added_count, note = run_detect(current, allow_param=True)
                            # Sammel neue Track Objekte
                            new_tracks = []
                            if clip and bpy is not None:
                                for t in clip.tracking.tracks:
                                    if id(t) not in pre_tracks:
                                        new_tracks.append(t)
                            # Distanzberechnung zu bestehenden (surviving) Tracks
                            accepted_names = []
                            removed_names = []
                            new_signatures = []
                            # Baue Liste existierender (akzeptierter) Positionen fuer Distanz
                            existing_positions_px = []
                            if clip and bpy is not None and w is not None and h is not None:
                                for t in clip.tracking.tracks:
                                    if id(t) in pre_tracks:  # nur alte Tracks
                                        try:
                                            marker_ref = None
                                            cur_frame_ctx = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
                                            if cur_frame_ctx is not None:
                                                for mm in t.markers:
                                                    if mm.frame == cur_frame_ctx:
                                                        marker_ref = mm
                                                        break
                                            if marker_ref is None and len(t.markers) > 0:
                                                marker_ref = t.markers[0]
                                            if marker_ref is None:
                                                continue
                                            co = marker_ref.co
                                            existing_positions_px.append((co[0]*w, co[1]*h))
                                        except Exception:  # noqa: BLE001
                                            pass
                            # Helper fuer Distance
                            def _nearest_dist_px(track_obj):
                                try:
                                    if w is None or h is None:
                                        return None
                                    marker_ref = None
                                    cur_frame_ctx = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
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
                                    px = co[0]*w
                                    py = co[1]*h
                                    if not existing_positions_px:
                                        return 10**9  # kein Vergleich => sehr groß
                                    return min(((px-ex)**2 + (py-ey)**2) for ex,ey in existing_positions_px)**0.5
                                except Exception:  # noqa: BLE001
                                    return None
                            # Filter nach Mindestdistanz
                            for t in new_tracks:
                                dist = _nearest_dist_px(t)
                                # Distanz None -> behandeln wie 0 (verwerfen) damit stabile Regel
                                if dist is None:
                                    keep = False
                                else:
                                    keep = dist >= md
                                if keep:
                                    accepted_names.append(t.name)
                                    # Position sofort zu Referenz hinzufuegen fuer Folgetracks
                                    try:
                                        if w is not None and h is not None:
                                            marker_ref = None
                                            cur_frame_ctx = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
                                            if cur_frame_ctx is not None:
                                                for mm in t.markers:
                                                    if mm.frame == cur_frame_ctx:
                                                        marker_ref = mm
                                                        break
                                            if marker_ref is None and len(t.markers) > 0:
                                                marker_ref = t.markers[0]
                                            if marker_ref is not None:
                                                co = marker_ref.co
                                                existing_positions_px.append((co[0]*w, co[1]*h))
                                    except Exception:  # noqa: BLE001
                                        pass
                                else:
                                    removed_names.append(t.name)
                            # Entferne verworfene Tracks physisch
                            if removed_names and clip and bpy is not None:
                                try:
                                    with context.temp_override(area=area, region=region):
                                        for nm in removed_names:
                                            trk = next((tt for tt in clip.tracking.tracks if tt.name == nm), None)
                                            if not trk:
                                                continue
                                            try:
                                                for tr in clip.tracking.tracks:
                                                    try: tr.select = False
                                                    except Exception: pass
                                                try: trk.select = True
                                                except Exception: pass
                                                try: clip.tracking.tracks.active = trk  # type: ignore[attr-defined]
                                                except Exception: pass
                                                bpy.ops.clip.delete_track()
                                            except Exception:
                                                pass
                                except Exception:
                                    pass
                            # Neue Signaturen akzeptierter Marker bestimmen
                            if clip:
                                for t in clip.tracking.tracks:
                                    if t.name in accepted_names:
                                        sig = _build_signature(t)
                                        if sig and sig not in new_signatures and sig not in seen_signatures:
                                            new_signatures.append(sig)
                            am = len(new_signatures)
                            if target_cnt is None:
                                # Akzeptieren ohne Ziel
                                for sig in new_signatures:
                                    seen_signatures.add(sig)
                                pass_new_signatures.append(new_signatures)
                                per_pass.append((current, am, f"attempt={attempt} md={md:.2f} (kein Ziel)"))
                                accepted = True
                                break
                            if am == target_cnt or (range_lo is not None and range_hi is not None and range_lo <= am <= range_hi):
                                for sig in new_signatures:
                                    seen_signatures.add(sig)
                                pass_new_signatures.append(new_signatures)
                                tag = "OK" if am == target_cnt else "RANGE_OK"
                                per_pass.append((current, am, f"attempt={attempt} md={md:.2f} {tag}"))
                                accepted = True
                                break
                            # Abweichung -> Bewertung und ggf. behalten besten Versuch falls Abbruch
                            diff = abs(am - target_cnt)
                            if best_attempt_diff is None or diff < best_attempt_diff:
                                # Snapshot besten Versuch (Signaturen + Namen) zur Notfall-Uebernahme
                                best_attempt_diff = diff
                                best_attempt_data = (list(new_signatures), am, md, attempt)
                            # Alle akzeptierten neuen Marker wieder loeschen (zur Wiederholung) wenn nicht letzter Versuch
                            if accepted is False and (attempt < max_attempts):
                                if accepted_names and clip and bpy is not None:
                                    try:
                                        with context.temp_override(area=area, region=region):
                                            for nm in accepted_names:
                                                trk = next((tt for tt in clip.tracking.tracks if tt.name == nm), None)
                                                if not trk: continue
                                                try:
                                                    for tr in clip.tracking.tracks:
                                                        try: tr.select = False
                                                        except Exception: pass
                                                    try: trk.select = True
                                                    except Exception: pass
                                                    try: clip.tracking.tracks.active = trk  # type: ignore[attr-defined]
                                                    except Exception: pass
                                                    bpy.ops.clip.delete_track()
                                                except Exception: pass
                                    except Exception:
                                        pass
                            # md anpassen gem. Formel: md = md * (am/za); Schutz vor Null
                            if target_cnt > 0:
                                if am == 0:
                                    md = md * 0.5  # fallback schrumpfen
                                else:
                                    md = md * (am / target_cnt)
                            # Guardrails
                            if md < 0.1: md = 0.1
                            if md > 10000: md = 10000
                            attempt += 1
                        # Ende Attempt-Loop
                        if not accepted:
                            # Nimm besten bisherigen Versuch, fuege dessen Signaturen hinzu (erneut detect nicht ausfuehren)
                            if best_attempt_data is not None:
                                best_sigs, best_am, best_md, best_att = best_attempt_data
                                # Wir muessen die Marker fuer den besten Versuch erneut erzeugen -> einfacher: letzten Versuch belassen falls noch vorhanden
                                # Falls geloescht, koennen wir sie nicht rekonstruieren ohne erneuten Detect -> Hinweis
                                per_pass.append((current, best_am, f"attempt={best_att} md~{best_md:.2f} BEST (kein exakter Treffer)"))
                                for sig in best_sigs:
                                    seen_signatures.add(sig)
                                pass_new_signatures.append(best_sigs)
                            else:
                                per_pass.append((current, 0, "keine Marker akzeptiert"))
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
                # Verwende run_detect auch hier, um identisches Logging zu gewoahrleisten
                before_known = set(seen_signatures)
                added, note = run_detect(current, allow_param=False)
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
                per_pass.append((current, added, note or 'fallback ohne threshold'))
                passes = 1
            else:
                cur_pattern_progressive = float(pattern_size) if pattern_size else None
                while current >= min_threshold and passes < max_passes:
                    if cur_pattern_progressive is not None:
                        apply_sizes(cur_pattern_progressive)
                    try:
                        before_known = set(seen_signatures)
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
                        if min_new_markers_per_pass is not None:
                            if len(new_sigs_this_pass) < min_new_markers_per_pass:
                                note_abort = (
                                    f"abgebrochen: neue Marker {len(new_sigs_this_pass)} < Mindestanzahl {min_new_markers_per_pass}"
                                )
                                per_pass[-1] = (
                                    per_pass[-1][0],
                                    per_pass[-1][1],
                                    (per_pass[-1][2] + ' | ' + note_abort).strip(),
                                )
                                aborted_due_to_min = True
                                break
                    except Exception:  # noqa: BLE001
                        per_pass.append((current, 0, 'fallback Fehler'))
                        break
                    passes += 1
                    current *= factor
                    if cur_pattern_progressive is not None:
                        cur_pattern_progressive *= 1.5
        removed_track_names = set()
        # Batch-Duplikatloeschung am Ende (robuster): nur wenn nicht immediate oder Reste
        if remove_duplicates and clip and bpy is not None and not immediate_delete:
            # Finde Kandidaten
            candidates = []
            for m in marker_logs:
                dist = m.get('nearest_dist_px')
                name = m['track_name']
                if keep_first_marker and m is marker_logs[0]:
                    continue
                if dist is None:
                    # Wenn keine Distanz und nicht erster Marker -> Duplikat
                    candidates.append(name)
                elif dist <= duplicate_tolerance_px:
                    candidates.append(name)
            # Entfernen
            if candidates:
                # Erster Durchlauf: Kontext-override versuchen
                def _delete_list(name_list):
                    removed_local = []
                    for nm in name_list:
                        trk = next((t for t in clip.tracking.tracks if t.name == nm), None)
                        if not trk:
                            continue
                        try:
                            _ensure_tracking_mode()
                            # Deselect all
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
                                # Manche Versionen erwarten keinen speziellen Kontext
                                bpy.ops.clip.delete_track()
                            # Pruefen ob wirklich weg:
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
                if removed_track_names:
                    _vprint(
                        f"[TrackingHelper] Entfernt {len(removed_track_names)} Tracks (Batch, tol={duplicate_tolerance_px}) : {sorted(removed_track_names)}"
                    )
                else:
                    _vprint("[TrackingHelper] Batch-Loeschung: keine Tracks entfernt (evtl. Kontextproblem oder keine echten Duplikate)")

        # Cluster-Konsolidierung (nach Duplikat-Phase), falls aktiviert
        cluster_removed = []
        cluster_info = None
        if cluster_consolidate and clip and bpy is not None:
            try:
                # Map Track-Name -> (order_index, (x,y)) unter Verwendung der marker_logs Reihenfolge
                name_order = {m['track_name']: i for i, m in enumerate(marker_logs)}
                track_positions = []
                if w is not None and h is not None:
                    for t in clip.tracking.tracks:
                        # Hole Marker-Koordinate (Frame current oder erster)
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
                # Sortiere nach Entstehungsreihenfolge (aus Logs), dann Name
                track_positions.sort(key=lambda x: (x[1], x[0]))
                tol2 = float(cluster_tolerance_px) ** 2
                clusters = []  # Liste: {center:(x,y), members:[name,...]}
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
                # Reduziere Cluster auf max_per_cluster
                to_remove_cluster = []
                for c in clusters:
                    members = c['members']
                    if len(members) > cluster_max_per_cluster:
                        # Behalte die ersten (nach Entstehungssortierung), entferne Rest
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
                # Cluster-Statistik
                cluster_info = {
                    'clusters_total': len(clusters),
                    'clusters_gt1': sum(1 for c in clusters if len(c['members']) > 1),
                    'removed_in_cluster': len(cluster_removed),
                    'tolerance_px': cluster_tolerance_px,
                    'max_per_cluster': cluster_max_per_cluster,
                }
                if cluster_removed:
                    _vprint(
                        f"[TrackingHelper] Cluster-Konsolidierung: entfernt {len(cluster_removed)} Tracks innerhalb Toleranz {cluster_tolerance_px}px (max_per_cluster={cluster_max_per_cluster})"
                    )
            except Exception as cl_err:  # noqa: BLE001
                _vprint(f"[TrackingHelper] Cluster-Konsolidierung Fehler: {cl_err}")
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
            'marker_logs': marker_logs
        }
    finally:
        # Urspruengliche Werte wiederherstellen
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

    # Filter: entfernte Tracks (Distanz None/0) nicht mehr in Statistik zoahlen
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
    per_pass_stats = {}
    for m in marker_logs:
        if m.get('nearest_dist_px') is None or m['track_name'] in removed_for_stats:
            continue
        p = m['pass']
        distances_per_pass.setdefault(p, []).append(m['nearest_dist_px'])
    for p, vals in distances_per_pass.items():
        per_pass_stats[p] = _compute_stats(vals)

    # Zusatz-Metriken: Zero-Distanzen (Marker exakt auf bestehender Position) sind erwartungsgemoaß hoaufig
    zero_count = sum(1 for d in distances_all if d == 0.0)
    positive_distances = [d for d in distances_all if d and d > 0.0]
    min_positive = min(positive_distances) if positive_distances else None
    positive_count = len(positive_distances)
    zero_ratio = (zero_count / len(distances_all)) if distances_all else None

    # Kurze Ausgabe zur Orientierung
    if VERBOSE_TRACKING_LOGS:
        try:
            _vprint(
                f"[TrackingHelper] Distanz Statistik gesamt: count={distance_stats['count']} min={distance_stats['min']} max={distance_stats['max']} "
                f"median={distance_stats['median']} mean={distance_stats['mean']}")
            if distances_all:
                _vprint(
                    f"[TrackingHelper] Distanz Verteilung: zeros={zero_count} ({zero_ratio:.2%} ) >0={positive_count} min_pos={min_positive}"
                )
            # Zusatz: Gruende fuer fehlende Distanzen, falls Diskrepanz auffoallig
            missing = [m for m in marker_logs if m.get('nearest_dist_px') is None and m['track_name'] not in removed_for_stats]
            if missing:
                reason_counter = {}
                for m in missing:
                    r = m.get('no_distance_reason') or 'unknown'
                    reason_counter[r] = reason_counter.get(r, 0) + 1
                reason_parts = ', '.join(f"{k}:{v}" for k, v in sorted(reason_counter.items()))
                _vprint(f"[TrackingHelper] Distanz fehlend fuer {len(missing)} Marker (Gruende: {reason_parts})")
        except Exception:  # noqa: BLE001
            pass

    # Erzeuge Liste der pro Pass neu hinzugekommenen Marker (nach evtl. Duplikat-/Clusterentfernung kann sie von per_pass Added abweichen)
    per_pass_new_counts = []
    # Jetzt (nach moeglichem Entfernen von Duplikaten & Clustern) finale Zaehler bestimmen
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
    per_pass_new_counts_internal = final_counts
    per_pass_new_counts.extend(per_pass_new_counts_internal)

    # Ausgabe jetzt erst, damit nur surviving Marker gezaehlt werden
    try:
        for idx, cnt in enumerate(per_pass_new_counts_internal, start=1):
            print(f"[Detect] Pass {idx} Marker={cnt}")
    except Exception:  # noqa: BLE001
        pass

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'per_pass': per_pass,
        'aborted_due_to_min': aborted_due_to_min,
    'dynamic_min_distance_px': dynamic_min_distance_px,
    'target_range_lower': target_range_lower,
    'target_range_upper': target_range_upper,
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
    }
