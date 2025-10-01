"""Hilfsfunktionen & Multi-Pass Feature Detection mit Marker-Limit.

Diese Datei war beschädigt und wurde konsolidiert/vereinfacht neu aufgebaut.
Funktionen:
 - Mehrfaches Detect mit absteigendem Threshold
 - Optionale Duplikatentfernung (Distanz <= Toleranz)
 - Optionale Cluster-Konsolidierung
 - HARTES LIMIT: Maximal 7 NEUE Marker werden behalten (frühzeitiger Abbruch, danach Ende)
 - Ausführliche Logs & Statistik

Hinweis: Die ursprüngliche hochkomplexe Distanz-/Logik wurde vereinfacht für Robustheit.
"""

from __future__ import annotations

try:  # Blender Umgebung
    import bpy  # type: ignore
except ImportError:  # außerhalb Blender
    bpy = None  # type: ignore

import traceback
from math import sqrt


MAX_NEW_MARKERS = 7  # globales hartes Limit neuer Marker pro Lauf


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


def _track_position_px(track, width, height, frame_current):
    marker = None
    if frame_current is not None:
        for m in track.markers:
            if m.frame == frame_current:
                marker = m
                break
    if marker is None and len(track.markers) > 0:
        marker = track.markers[0]
    if not marker:
        return None
    try:
        x, y = marker.co
        return (x * width, y * height)
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
    immediate_delete=False,  # ignoriert in vereinfachter Version (immer Batch)
    cluster_consolidate=False,
    cluster_tolerance_px=2.0,
    cluster_max_per_cluster=1,
):
    """Fuehrt mehrfache Feature-Erkennung aus und begrenzt NEUE Marker auf MAX_NEW_MARKERS.

    Rueckgabe: dict mit Kennzahlen analog zur vorherigen Version (vereinfacht wo noetig).
    """
    area = find_clip_editor_area(context)
    if area is None:
        return {'success': False, 'message': 'Kein Movie Clip Editor Bereich gefunden.'}
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return {'success': False, 'message': 'Keine WINDOW Region im Clip Editor gefunden.'}

    clip = get_clip_from_area(area)
    if not clip:
        return {'success': False, 'message': 'Kein aktiver Clip im Clip Editor.'}

    # Bildgroesse & Pattern/Search Size anpassen
    pattern_size = None
    search_size = None
    old_pattern = None
    old_search = None
    settings = getattr(clip.tracking, 'settings', None)
    try:
        w, h = clip.size
    except Exception:  # noqa: BLE001
        w, h = None, None
    if w:
        pattern_size = max(3, int(round(w * 0.01)))
        search_size = pattern_size * 2
        if settings is not None:
            old_pattern = getattr(settings, 'default_pattern_size', None)
            old_search = getattr(settings, 'default_search_size', None)
            if hasattr(settings, 'default_pattern_size'):
                settings.default_pattern_size = pattern_size
            if hasattr(settings, 'default_search_size'):
                settings.default_search_size = search_size

    # Originale Tracks merken (IDs & Namen)
    original_ids = {id(t) for t in clip.tracking.tracks}
    original_names = {t.name for t in clip.tracking.tracks}
    tracks_before = len(original_ids)

    # Threshold-Faehigkeit pruefen
    has_threshold = False
    if bpy is not None:
        try:
            rna = bpy.ops.clip.detect_features.get_rna_type()
            has_threshold = 'threshold' in rna.properties.keys()
        except Exception:  # noqa: BLE001
            has_threshold = False

    # Sanitizing Parameter
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

    passes = 0
    current_thr = start_threshold
    per_pass = []  # (thr, effective_added, note)
    marker_logs = []  # einfache Logliste
    raw_total_added = 0
    raw_per_pass = []
    removed_duplicate_tracks = []
    removed_cluster_tracks = []
    max_limit_removed_tracks = []

    def _run_detect(thr):
        before = len(clip.tracking.tracks)
        note = ''
        try:
            if has_threshold:
                bpy.ops.clip.detect_features(threshold=thr)
            else:
                bpy.ops.clip.detect_features()
                note = 'no_thr_param'
        except Exception as de:  # noqa: BLE001
            note = f'err:{type(de).__name__}'
        after = len(clip.tracking.tracks)
        return after - before, note

    def _log_new(thr, pass_index):
        # Reihenfolge/IDs loggen
        for t in clip.tracking.tracks:
            if id(t) not in original_ids and not any(m['name'] == t.name for m in marker_logs):
                marker_logs.append({'pass': pass_index, 'threshold': thr, 'name': t.name})

    def _net_new_ids():
        return [t for t in clip.tracking.tracks if id(t) not in original_ids]

    def _enforce_limit(final=False):
        # Haelt nur die ersten MAX_NEW_MARKERS (nach Entstehung laut marker_logs)
        new_tracks = _net_new_ids()
        if len(new_tracks) <= MAX_NEW_MARKERS:
            return 0
        # Sortiere nach Reihenfolge in marker_logs
        order = {m['name']: i for i, m in enumerate(marker_logs)}
        survivors = sorted(new_tracks, key=lambda t: order.get(t.name, 10**9))[:MAX_NEW_MARKERS]
        keep_names = {t.name for t in survivors}
        to_delete = [t for t in new_tracks if t.name not in keep_names]
        removed_names = []
        for trk in to_delete:
            try:
                for t2 in clip.tracking.tracks:
                    try:
                        t2.select = False
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    trk.select = True
                except Exception:  # noqa: BLE001
                    pass
                clip.tracking.tracks.active = trk  # type: ignore[attr-defined]
                bpy.ops.clip.delete_track()
                removed_names.append(trk.name)
            except Exception:  # noqa: BLE001
                pass
        if removed_names:
            max_limit_removed_tracks.extend(removed_names)
            print(f"[TrackingHelper] LIMIT entfernt {len(removed_names)} Marker -> {removed_names}")
        return len(removed_names)

    def _remove_duplicates():
        if not remove_duplicates or duplicate_tolerance_px < 0:
            return []
        frame_cur = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
        width = w or 1
        height = h or 1
        tol = duplicate_tolerance_px
        kept = []
        removed = []
        for t in list(clip.tracking.tracks):
            if id(t) in original_ids and keep_first_marker:
                kept.append(t)
                continue
            pos = _track_position_px(t, width, height, frame_cur)
            if not pos:
                # Keine Position -> als Duplikat behandeln (falls nicht erster)
                if keep_first_marker and not kept:
                    kept.append(t)
                else:
                    try:
                        for tt in clip.tracking.tracks:
                            tt.select = False
                        t.select = True
                        clip.tracking.tracks.active = t  # type: ignore[attr-defined]
                        bpy.ops.clip.delete_track()
                        removed.append(t.name)
                    except Exception:  # noqa: BLE001
                        pass
                continue
            is_dup = False
            for kt in kept:
                kpos = _track_position_px(kt, width, height, frame_cur)
                if not kpos:
                    continue
                dx = pos[0] - kpos[0]
                dy = pos[1] - kpos[1]
                if sqrt(dx*dx + dy*dy) <= tol:
                    is_dup = True
                    break
            if is_dup:
                try:
                    for tt in clip.tracking.tracks:
                        tt.select = False
                    t.select = True
                    clip.tracking.tracks.active = t  # type: ignore[attr-defined]
                    bpy.ops.clip.delete_track()
                    removed.append(t.name)
                except Exception:  # noqa: BLE001
                    pass
            else:
                kept.append(t)
        if removed:
            print(f"[TrackingHelper] Duplikate entfernt: {removed}")
        return removed

    def _cluster_consolidate():
        if not cluster_consolidate or cluster_tolerance_px <= 0:
            return []
        frame_cur = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
        width = w or 1
        height = h or 1
        # Sammle Positionen
        entries = []  # (name, order_idx, x, y)
        order = {m['name']: i for i, m in enumerate(marker_logs)}
        for t in clip.tracking.tracks:
            pos = _track_position_px(t, width, height, frame_cur)
            if not pos:
                continue
            entries.append((t.name, order.get(t.name, 10**9), pos[0], pos[1]))
        entries.sort(key=lambda x: (x[1], x[0]))
        clusters = []  # list of dict(center=(x,y), members=[name,...])
        r2 = cluster_tolerance_px * cluster_tolerance_px
        for nm, _, x, y in entries:
            placed = False
            for c in clusters:
                cx, cy = c['center']
                if (x - cx)**2 + (y - cy)**2 <= r2:
                    c['members'].append(nm)
                    placed = True
                    break
            if not placed:
                clusters.append({'center': (x, y), 'members': [nm]})
        to_remove = []
        for c in clusters:
            if len(c['members']) > cluster_max_per_cluster:
                # entferne spätere
                to_remove.extend(c['members'][cluster_max_per_cluster:])
        removed = []
        for nm in to_remove:
            trk = next((t for t in clip.tracking.tracks if t.name == nm), None)
            if not trk:
                continue
            try:
                for tt in clip.tracking.tracks:
                    tt.select = False
                trk.select = True
                clip.tracking.tracks.active = trk  # type: ignore[attr-defined]
                bpy.ops.clip.delete_track()
                removed.append(nm)
            except Exception:  # noqa: BLE001
                pass
        if removed:
            print(f"[TrackingHelper] Cluster entfernt: {removed}")
        return removed

    try:
        with context.temp_override(area=area, region=region):
            while current_thr >= min_threshold and passes < max_passes:
                added_raw, note = _run_detect(current_thr)
                raw_total_added += added_raw
                raw_per_pass.append(added_raw)
                passes += 1
                _log_new(current_thr, passes)
                # Enforce Limit direkt nach Pass (falls schon erreicht -> abbrechen)
                _enforce_limit()
                effective_new = len(_net_new_ids())
                per_pass.append((current_thr, effective_new, note))
                if effective_new >= MAX_NEW_MARKERS:
                    print(f"[TrackingHelper] Limit {MAX_NEW_MARKERS} erreicht – Abbruch weiterer Pässe.")
                    break
                current_thr *= factor
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
        }
    finally:
        # Pattern/Search zurücksetzen
        if settings is not None:
            try:
                if old_pattern is not None and hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = old_pattern
                if old_search is not None and hasattr(settings, 'default_search_size'):
                    settings.default_search_size = old_search
            except Exception:  # noqa: BLE001
                pass

    # Nach allen Pässen: Duplikate & Cluster (Reihenfolge: Duplikate -> Cluster) und dann Limit erneut
    removed_duplicate_tracks = _remove_duplicates() if remove_duplicates else []
    removed_cluster_tracks = _cluster_consolidate() if cluster_consolidate else []
    _enforce_limit(final=True)

    final_new = len(_net_new_ids())
    total_added = final_new  # Netto neue Marker

    # Basic Distanzstatistik (vereinfacht): Distanz zwischen neuen Markern (paarweise minimal, optional)
    distance_stats = {'count': 0, 'min': None, 'max': None, 'mean': None, 'median': None}
    per_pass_distance_stats = {}

    summary_log = (
        f"[TrackingHelper] Zusammenfassung: Passes={passes} neu={final_new} raw_total={raw_total_added} "
        f"Dupl={len(removed_duplicate_tracks)} Cluster={len(removed_cluster_tracks)} LimitEntf={len(max_limit_removed_tracks)}"
    )
    print(summary_log)

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
        'per_pass_distance_stats': per_pass_distance_stats,
        'removed_duplicate_tracks': removed_duplicate_tracks,
        'removed_duplicate_count': len(removed_duplicate_tracks),
        'cluster_removed_tracks': removed_cluster_tracks,
        'cluster_removed_count': len(removed_cluster_tracks),
        'cluster_stats': None,
        'max_limit_removed_tracks': max_limit_removed_tracks,
        'max_limit_removed_count': len(max_limit_removed_tracks),
        'raw_total_added': raw_total_added,
        'raw_per_pass': raw_per_pass,
    }


    # Pruefen ob threshold unterstuetzt wird
    has_threshold = False
    if bpy is not None:
        try:
            rna = bpy.ops.clip.detect_features.get_rna_type()
            has_threshold = 'threshold' in rna.properties.keys()
        except Exception:  # noqa: BLE001
            has_threshold = False

    # Sichere Konvertierung der moeglicherweise als Property uebergebenen Werte
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

    per_pass = []  # Liste von Tuplen (threshold, effective_added_count, note)
    passes = 0
    current = start_threshold
    marker_logs = []  # speichert detailinformationen neuer Marker
    existing_track_ids = set()
    if clip and bpy is not None:
        existing_track_ids = {id(t) for t in clip.tracking.tracks}

    # Maximalzahl neuer Marker (global neu gegenüber Start) – nach jedem Pass wird gekappt
    MAX_NEW_MARKERS = 7
    # Sammelliste der pro Limit entfernten Track-Namen (über alle Passes)
    limit_removed = []

    def _count_net_new():
        if not (clip and bpy is not None):
            return 0
        try:
            return sum(1 for t in clip.tracking.tracks if id(t) not in original_track_ids_snapshot)
        except Exception:  # noqa: BLE001
            return 0

    raw_total_added = 0  # Summe aller rohen Additionen (vor Kappung)
    raw_per_pass = []  # Liste roher Additionen

    def _enforce_limit():  # noqa: C901
        """Kappung nach jedem Pass: nur die ersten MAX_NEW_MARKERS neu entstandenen Tracks behalten.
        Entscheidung: Behalte aeltere (frühere Passes = stärkere Features)."""
        if not (clip and bpy is not None):
            return 0
        try:
            current_tracks = list(clip.tracking.tracks)
            # Reihenfolge der Entstehung laut marker_logs (nur nicht bereits geloeschte Einträge)
            ordered_new_names = []
            seen = set()
            for m in marker_logs:
                nm = m['track_name']
                if nm in seen:
                    continue
                seen.add(nm)
                # existiert noch und ist wirklich neu?
                trk = next((t for t in current_tracks if t.name == nm), None)
                if not trk:
                    continue
                if id(trk) in original_track_ids_snapshot:
                    continue  # war schon vorher da
                ordered_new_names.append(nm)
            if len(ordered_new_names) <= MAX_NEW_MARKERS:
                return 0
            keep = set(ordered_new_names[:MAX_NEW_MARKERS])
            to_remove = [nm for nm in ordered_new_names if nm not in keep]
            removed_local = []
            def _delete_names(name_list):
                removed_del = []
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
                            removed_del.append(nm)
                    except Exception:  # noqa: BLE001
                        pass
                return removed_del
            try:
                with context.temp_override(area=area, region=region):
                    removed_local = _delete_names(to_remove)
            except Exception:
                removed_local = _delete_names(to_remove)
            if removed_local:
                limit_removed.extend(removed_local)
                print(f"[TrackingHelper] Per-Pass Limit-Kappung: entfernt {len(removed_local)} Marker (Limit={MAX_NEW_MARKERS}) -> {removed_local}")
            return len(removed_local)
        except Exception as _lim_err:  # noqa: BLE001
            print(f"[TrackingHelper] Limit-Kappung Fehler: {_lim_err}")
            return 0

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
                                print(
                                    f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} DUPLIKAT ENTFERNT '{t.name}' dist={nearest_dist_px} (immediate)"
                                )
                                continue
                            except Exception:  # noqa: BLE001
                                removed_immediately = False
                        except Exception:  # noqa: BLE001
                            removed_immediately = False
                try:
                    print(
                        f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} NEUER TRACK '{safe_name}' "
                        f"frame={frame_used} pos_norm={marker_co_norm} pos_px={marker_px} nearest_px={nearest_dist_px} pattern={pattern_size} search={search_size}"
                    )
                except UnicodeDecodeError as ue_print:  # should not happen now
                    print(f"[TrackingHelper][WARN] Unicode problem beim Drucken eines Track-Namens: {ue_print}")
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
                    added, note = run_detect(current, allow_param=False)
                    # Log erst nach Detect
                    log_new_tracks(passes + 1, current)
                    per_pass.append((current, added, note or 'kein threshold Param'))
                    passes = 1
                else:
                    cur_pattern_progressive = float(pattern_size) if pattern_size else None
                    net_prev = _count_net_new()
                    while current >= min_threshold and passes < max_passes:
                        if cur_pattern_progressive is not None:
                            apply_sizes(cur_pattern_progressive)
                        added, note = run_detect(current, allow_param=True)
                        raw_total_added_local = added
                        raw_total_added += raw_total_added_local
                        raw_per_pass.append(raw_total_added_local)
                        log_new_tracks(passes + 1, current)
                        removed_now = _enforce_limit()  # Kappung
                        net_now = _count_net_new()
                        effective_added = max(0, net_now - net_prev)
                        net_prev = net_now
                        if removed_now or effective_added != added:
                            if removed_now:
                                note = (note + ';trim') if note else 'trim'
                            if effective_added != added:
                                note = (note + f";raw:{added}") if note else f"raw:{added}"
                        per_pass.append((current, effective_added, note))
                        passes += 1
                        current *= factor
                        if cur_pattern_progressive is not None:
                            cur_pattern_progressive *= 1.15
                    # Kein Early Stop mehr – vollständige Schleife oder min_threshold erreicht
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            if not has_threshold:
                apply_sizes(pattern_size)
                # Verwende run_detect auch hier, um identisches Logging zu gewoahrleisten
                added, note = run_detect(current, allow_param=False)
                log_new_tracks(passes + 1, current)
                per_pass.append((current, added, note or 'fallback ohne threshold'))
                passes = 1
            else:
                cur_pattern_progressive = float(pattern_size) if pattern_size else None
                net_prev = _count_net_new()
                while current >= min_threshold and passes < max_passes:
                    if cur_pattern_progressive is not None:
                        apply_sizes(cur_pattern_progressive)
                    try:
                        added, note = run_detect(current, allow_param=True)
                        raw_total_added_local = added
                        raw_total_added += raw_total_added_local
                        raw_per_pass.append(raw_total_added_local)
                        log_new_tracks(passes + 1, current)
                        removed_now = _enforce_limit()
                        net_now = _count_net_new()
                        effective_added = max(0, net_now - net_prev)
                        net_prev = net_now
                        if removed_now or effective_added != added:
                            if removed_now:
                                note = (note + ';trim') if note else 'trim'
                            if effective_added != added:
                                note = (note + f";raw:{added}") if note else f"raw:{added}"
                        per_pass.append((current, effective_added, (note or 'fallback')))
                    except Exception:  # noqa: BLE001
                        per_pass.append((current, 0, 'fallback Fehler'))
                        break
                    passes += 1
                    current *= factor
                    if cur_pattern_progressive is not None:
                        cur_pattern_progressive *= 1.5
                # Kein Early Stop mehr
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
                    print(
                        f"[TrackingHelper] Entfernt {len(removed_track_names)} Tracks (Batch, tol={duplicate_tolerance_px}) : {sorted(removed_track_names)}"
                    )
                else:
                    print("[TrackingHelper] Batch-Loeschung: keine Tracks entfernt (evtl. Kontextproblem oder keine echten Duplikate)")

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
                    print(
                        f"[TrackingHelper] Cluster-Konsolidierung: entfernt {len(cluster_removed)} Tracks innerhalb Toleranz {cluster_tolerance_px}px (max_per_cluster={cluster_max_per_cluster})"
                    )
            except Exception as cl_err:  # noqa: BLE001
                print(f"[TrackingHelper] Cluster-Konsolidierung Fehler: {cl_err}")

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
        total_added = len(clip.tracking.tracks) - tracks_before  # effektive Netto-Anzahl
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
    try:
        print(
            f"[TrackingHelper] Distanz Statistik gesamt: count={distance_stats['count']} min={distance_stats['min']} max={distance_stats['max']} "
            f"median={distance_stats['median']} mean={distance_stats['mean']}")
        if distances_all:
            print(
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
            print(f"[TrackingHelper] Distanz fehlend fuer {len(missing)} Marker (Gruende: {reason_parts})")
        # Abschluss-Gesamtlog mit Marker-Anzahlen
        final_total = len(clip.tracking.tracks) if clip else -1
        dup_removed_cnt = len(removed_track_names) if 'removed_track_names' in locals() else 0
        cluster_removed_cnt = len(cluster_removed) if 'cluster_removed' in locals() else 0
        limit_removed_cnt = len(limit_removed) if 'limit_removed' in locals() else 0
        remaining_new = max(0, final_total - len(original_track_names)) if final_total >= 0 else '?'
        if isinstance(remaining_new, int) and remaining_new > MAX_NEW_MARKERS:
            # Falls trotz Kappung noch mehr da (z.B. Umbenennungen / Ersetzungen) -> Warnung
            print(f"[TrackingHelper][WARN] Limit {MAX_NEW_MARKERS} überschritten (remaining_new={remaining_new}) – unerwartet.")
        print(
            f"[TrackingHelper] Marker Zusammenfassung: vorher={tracks_before} final={final_total} roh_neu={total_added} "
            f"entfernt(Dupl={dup_removed_cnt},Cluster={cluster_removed_cnt},Limit={limit_removed_cnt}) verbleibend_neu={remaining_new} (Limit={MAX_NEW_MARKERS})"
        )
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
        'max_limit_removed_tracks': sorted(limit_removed) if 'limit_removed' in locals() else [],
        'max_limit_removed_count': len(limit_removed) if 'limit_removed' in locals() else 0,
        'raw_total_added': raw_total_added,
        'raw_per_pass': raw_per_pass,
    }
