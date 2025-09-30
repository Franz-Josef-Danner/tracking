import bpy


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
    min_distance_px=6.0,
    debug=False,
    use_overlap=True,
    overlap_threshold=0.2,
    tag_pass_names=True,
    rounding_step=0.25,
    cluster_cleanup=True,
    cluster_use_pattern=True,
):
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
    tracks_before = len(clip.tracking.tracks) if clip else -1

    # Prüfen ob threshold unterstützt wird
    try:
        rna = bpy.ops.clip.detect_features.get_rna_type()
        has_threshold = 'threshold' in rna.properties.keys()
    except Exception:  # noqa: BLE001
        has_threshold = False

    def _as_float(val, default):
        if isinstance(val, (int, float)):
            return float(val)
        # Versuche 'value' oder 'default' Attribut (Blender Property Platzhalter)
        for attr in ('value', 'default'):
            try:
                candidate = getattr(val, attr)
                if isinstance(candidate, (int, float)):
                    return float(candidate)
            except Exception:  # noqa: BLE001
                pass
        try:
            return float(val)
        except Exception:  # noqa: BLE001
            return float(default)

    start_threshold = _as_float(start_threshold, 1.0)
    min_threshold = _as_float(min_threshold, 0.0001)
    factor = _as_float(factor, 0.5)
    overlap_threshold = _as_float(overlap_threshold, 0.2)
    min_distance_px = _as_float(min_distance_px, 6.0)
    rounding_step = _as_float(rounding_step, 0.25)

    if min_distance_px < 0.1:
        min_distance_px = 0.1
    if factor <= 0.0 or factor >= 1.0:
        # Sicherheitswert
        factor = 0.5
    if min_threshold <= 0.0:
        min_threshold = 0.0001
    if start_threshold <= 0.0:
        start_threshold = 1.0
    if overlap_threshold <= 0.0:
        overlap_threshold = 0.2

    def _d(msg):
        if debug:
            print(f"[TrackingDetect] {msg}")

    per_pass = []  # Elemente: (threshold, added, removed, note)
    passes = 0
    current = start_threshold

    def _get_marker_center(track, frame_current, w, h):
        """Finde Marker im gegebenen Frame; fallback: erster Marker. Liefert Pixel-Koordinaten (float)."""
        try:
            for mk in track.markers:
                if mk.frame == frame_current:
                    cx, cy = mk.co
                    return cx * w, cy * h
            mk0 = track.markers[0]
            cx, cy = mk0.co
            return cx * w, cy * h
        except Exception:  # noqa: BLE001
            return None

    def _get_pattern_bbox(track, frame_current, w, h):
        """Berechne Bounding Box des Pattern in Pixeln. Gibt (xmin, ymin, xmax, ymax) oder None."""
        try:
            marker = None
            for mk in track.markers:
                if mk.frame == frame_current:
                    marker = mk
                    break
            if marker is None:
                marker = track.markers[0]
            cx, cy = marker.co
            # pattern_corners sind relative Offsets (laut API); deshalb addieren
            xs = []
            ys = []
            for corner in marker.pattern_corners:
                px = (cx + corner[0]) * w
                py = (cy + corner[1]) * h
                xs.append(px)
                ys.append(py)
            return min(xs), min(ys), max(xs), max(ys)
        except Exception:  # noqa: BLE001
            return None

    def _bbox_overlap_ratio(box_a, box_b):
        if not box_a or not box_b:
            return 0.0
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0
        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        if area_a <= 0 or area_b <= 0:
            return 0.0
        # Verwende Verhältnis zur kleineren Fläche (robuster wenn Größen variieren)
        return inter_area / min(area_a, area_b)

    def _round_coord(v: float) -> float:
        if rounding_step and rounding_step > 0.0:
            return round(v / rounding_step) * rounding_step
        return v

    def _collect_track_centers(frame_current):
        centers = []
        if not clip:
            return centers
        w, h = clip.size
        for tr in clip.tracking.tracks:
            pos = _get_marker_center(tr, frame_current, w, h)
            if pos is None:
                continue
            x, y = pos
            xq = _round_coord(x)
            yq = _round_coord(y)
            centers.append((tr.name, xq, yq))
        return centers

    def _calc_centers_for_tracks(track_list, frame_current):
        if not clip:
            return []
        w, h = clip.size
        centers = []
        for tr in track_list:
            pos = _get_marker_center(tr, frame_current, w, h)
            if pos is None:
                continue
            x, y = pos
            xq = _round_coord(x)
            yq = _round_coord(y)
            centers.append((tr, xq, yq))
        return centers

    def _remove_overlapping(prev_tracks, new_tracks, frame_current):
        if not clip or not new_tracks or not prev_tracks:
            return 0
        removed = 0
        min_dist_sq = min_distance_px * min_distance_px
        prev_centers = _calc_centers_for_tracks(prev_tracks, frame_current)
        w, h = clip.size
        # Precompute prev bboxes if overlap mode
        prev_bboxes = {}
        if use_overlap:
            for tr_prev in prev_tracks:
                prev_bboxes[tr_prev] = _get_pattern_bbox(tr_prev, frame_current, w, h)
        to_delete = []
        for tr in new_tracks:
            pos = _get_marker_center(tr, frame_current, w, h)
            if pos is None:
                continue
            x, y = pos
            xq = _round_coord(x)
            yq = _round_coord(y)
            bbox_new = _get_pattern_bbox(tr, frame_current, w, h) if use_overlap else None
            for _tr_old, ox, oy in prev_centers:
                dx = xq - ox
                dy = yq - oy
                dist_hit = (dx * dx + dy * dy) <= min_dist_sq
                overlap_hit = False
                if use_overlap and not dist_hit:
                    bbox_old = prev_bboxes.get(_tr_old)
                    if bbox_old and bbox_new:
                        overlap_ratio = _bbox_overlap_ratio(bbox_new, bbox_old)
                        overlap_hit = overlap_ratio >= overlap_threshold
                if dist_hit or overlap_hit:
                    to_delete.append(tr)
                    if debug:
                        _d(f"Remove new track '{tr.name}' reason=" + ("dist" if dist_hit else f"overlap >= {overlap_threshold}"))
                    break
        for tr in to_delete:
            try:
                clip.tracking.tracks.remove(tr)
                removed += 1
            except Exception:  # noqa: BLE001
                pass
        return removed

    def _remove_within_new(new_tracks, frame_current):
        if not clip or not new_tracks:
            return 0
        w, h = clip.size
        centers = []  # list of (track, xq, yq)
        for tr in new_tracks:
            pos = _get_marker_center(tr, frame_current, w, h)
            if pos is None:
                continue
            x, y = pos
            xq = _round_coord(x)
            yq = _round_coord(y)
            centers.append((tr, xq, yq))
        removed = 0
        min_dist_sq = min_distance_px * min_distance_px
        kept = []
        for tr, xq, yq in centers:
            duplicate = False
            for _ktr, kx, ky in kept:
                dx = xq - kx
                dy = yq - ky
                dist_hit = (dx * dx + dy * dy) <= min_dist_sq
                overlap_hit = False
                if use_overlap and not dist_hit:
                    # compute overlap if both boxes exist
                    bbox_a = _get_pattern_bbox(tr, frame_current, w, h)
                    bbox_b = _get_pattern_bbox(_ktr, frame_current, w, h)
                    if bbox_a and bbox_b:
                        if _bbox_overlap_ratio(bbox_a, bbox_b) >= overlap_threshold:
                            overlap_hit = True
                if dist_hit or overlap_hit:
                    # Delete this duplicate
                    try:
                        clip.tracking.tracks.remove(tr)
                        removed += 1
                    except Exception:  # noqa: BLE001
                        pass
                    duplicate = True
                    if debug:
                        _d(f"Remove intra-pass track '{tr.name}' reason=" + ("dist" if dist_hit else f"overlap >= {overlap_threshold}"))
                    break
            if not duplicate:
                kept.append((tr, xq, yq))
        return removed

    def run_detect(pass_index, thr, allow_param=True):
        if not clip:
            return 0, 0, 0, 'kein Clip'
        prev_tracks = list(clip.tracking.tracks)
        prev_ids = set(id(t) for t in prev_tracks)
        note = ''
        try:
            if has_threshold and allow_param:
                bpy.ops.clip.detect_features(threshold=thr)
            else:
                bpy.ops.clip.detect_features()
                if allow_param and not has_threshold:
                    note = 'threshold nicht unterstützt'
        except TypeError:
            bpy.ops.clip.detect_features()
            note = 'TypeError threshold'
        except Exception as e:  # noqa: BLE001
            return 0, 0, 0, f'Fehler detect: {e}'
        after_tracks = list(clip.tracking.tracks)
        new_tracks = [t for t in after_tracks if id(t) not in prev_ids]

        # Pass-Tagging (vor Duplikat-Löschung, damit Name konsistent für Analyse bleibt)
        if tag_pass_names and new_tracks:
            for t in new_tracks:
                try:
                    t.name = f"P{pass_index}_{t.name}"
                except Exception:  # noqa: BLE001
                    pass

        added = len(new_tracks)
        removed_prev = _remove_overlapping(prev_tracks, new_tracks, context.scene.frame_current)
        # Nach Entfernen, filtere verbliebene "neue" erneut (da einige gelöscht wurden)
        after_tracks2 = list(clip.tracking.tracks)
        new_tracks_remaining = [t for t in after_tracks2 if id(t) not in prev_ids]
        removed_new = _remove_within_new(new_tracks_remaining, context.scene.frame_current)
        # Diagnostik: Rest-Paare unter Mindestabstand (sollten 0 sein)
        residual_close = 0
        if debug and (removed_prev + removed_new) == 0 and added > 0:
            # Prüfe neue (nach Löschungen) gegen vorherige Tracks
            w, h = clip.size
            final_new = [t for t in clip.tracking.tracks if id(t) not in prev_ids]
            prev_centers_full = _calc_centers_for_tracks(prev_tracks, context.scene.frame_current)
            min_dist_sq = min_distance_px * min_distance_px
            for tr in final_new:
                pos = _get_marker_center(tr, context.scene.frame_current, w, h)
                if pos is None:
                    continue
                x, y = pos
                xq = _round_coord(x)
                yq = _round_coord(y)
                for _tr_old, ox, oy in prev_centers_full:
                    dx = xq - ox
                    dy = yq - oy
                    if (dx * dx + dy * dy) <= min_dist_sq:
                        residual_close += 1
                        _d(f"WARN: verbleibender Track '{tr.name}' dist<={min_distance_px} zu '{_tr_old.name if hasattr(_tr_old,'name') else _tr_old}' (Δ=({dx:.2f},{dy:.2f}))")
                        break
        _d(f"Pass {pass_index} thr={thr:.6f} added={added} removed_prev={removed_prev} removed_new={removed_new} residual_close={residual_close} min_dist={min_distance_px} overlap_thr={overlap_threshold} use_overlap={use_overlap} rounding_step={rounding_step}")
        return added, removed_prev, removed_new, note

    try:
        try:
            # Prefer temp_override
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    added, removed_prev, removed_new, note = run_detect(1, current, allow_param=False)
                    per_pass.append((current, added, removed_prev + removed_new, note or 'kein threshold Param'))
                    passes = 1
                else:
                    while current >= min_threshold and passes < max_passes:
                        added, removed_prev, removed_new, note = run_detect(passes + 1, current, allow_param=True)
                        per_pass.append((current, added, removed_prev + removed_new, note))
                        passes += 1
                        current *= factor
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            if not has_threshold:
                added, removed_prev, removed_new, note = run_detect(1, current, allow_param=False)
                per_pass.append((current, added, removed_prev + removed_new, (note or '') + ' fallback ohne threshold'))
                passes = 1
            else:
                while current >= min_threshold and passes < max_passes:
                    added, removed_prev, removed_new, note = run_detect(passes + 1, current, allow_param=True)
                    per_pass.append((current, added, removed_prev + removed_new, note + ' fallback'))
                    passes += 1
                    current *= factor
    except Exception as e:  # noqa: BLE001
        return {
            'success': False,
            'message': f'Fehler: {e}',
            'passes': passes,
            'total_added': -1,
            'per_pass': per_pass
        }

    if clip:
        total_added = len(clip.tracking.tracks) - tracks_before
    else:
        total_added = -1

    # Gesamt entfernte Duplikate zählen
    total_removed = sum(r for _t, _a, r, _n in per_pass)

    # Optionaler globaler Cluster-Cleanup nachdem alle Pässe durchlaufen wurden
    if cluster_cleanup and clip and total_added > 0:
        try:
            w, h = clip.size
            # Sammle (track, center, bbox, area)
            items = []
            for tr in list(clip.tracking.tracks):
                ctr = _get_marker_center(tr, context.scene.frame_current, w, h)
                if not ctr:
                    continue
                bbox = _get_pattern_bbox(tr, context.scene.frame_current, w, h)
                if bbox:
                    ax1, ay1, ax2, ay2 = bbox
                    area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
                else:
                    area = 1.0
                items.append((tr, ctr, bbox, area))
            # Sortiere stabil: frühere Namen (frühere Pässe) zuerst behalten
            items.sort(key=lambda x: x[0].name)
            effective_min_dist = min_distance_px
            removed_cluster = 0
            kept = []  # list of (ctr, bbox, area, track)
            for tr, (cx, cy), bbox, area in items:
                # Dynamischer Abstand: falls Pattern größer als min_distance
                local_min = effective_min_dist
                if cluster_use_pattern and bbox:
                    ax1, ay1, ax2, ay2 = bbox
                    pw = ax2 - ax1
                    ph = ay2 - ay1
                    # Verwende diagonale / 2 als Schätzwert für halbe Pattern-Ausdehnung
                    import math
                    pattern_radius = 0.5 * math.sqrt(pw * pw + ph * ph)
                    if pattern_radius > local_min:
                        local_min = pattern_radius
                local_min_sq = local_min * local_min
                conflict = False
                for (ocx, ocy), obox, oarea, otr in ((k[0], k[1], k[2], k[3]) for k in [((kc[0], kc[1]), kb, ka, kt) for kc, kb, ka, kt in [((kctr[0], kctr[1]), kbbox, karea, ktrack) for kctr, kbbox, karea, ktrack in kept]]):
                    dx = cx - ocx
                    dy = cy - ocy
                    if (dx * dx + dy * dy) <= local_min_sq:
                        conflict = True
                        break
                if conflict:
                    try:
                        clip.tracking.tracks.remove(tr)
                        removed_cluster += 1
                        if debug:
                            _d(f"Cluster remove '{tr.name}' local_min={local_min:.2f}")
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    kept.append(((cx, cy), bbox, area, tr))
            if debug:
                _d(f"Cluster-Cleanup entfernt {removed_cluster} Tracks (effektiver min_dist Basis={min_distance_px})")
            total_removed += removed_cluster
        except Exception as e:  # noqa: BLE001
            if debug:
                _d(f"Cluster-Cleanup Fehler: {e}")

    _d(f"Fertig: passes={passes} total_added={total_added} total_removed={total_removed} min_distance={min_distance_px} start_thr={start_threshold} min_thr={min_threshold} factor={factor} overlap_thr={overlap_threshold}")
    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'total_removed': total_removed,
        'per_pass': per_pass,
        'min_distance_px': min_distance_px,
    }
