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
