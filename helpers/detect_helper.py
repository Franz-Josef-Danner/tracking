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

    # Defensive Cast für Fälle, in denen versehentlich ein Property-Objekt weitergereicht wird
    try:
        if not isinstance(min_distance_px, (int, float)):
            # Versuche typische Attribute eines Blender Property Platzhalters
            candidate = getattr(min_distance_px, 'default', None)
            if isinstance(candidate, (int, float)):
                min_distance_px = candidate
            else:
                min_distance_px = 6.0
    except Exception:  # noqa: BLE001
        min_distance_px = 6.0

    try:
        min_distance_px = float(min_distance_px)
    except Exception:  # noqa: BLE001
        min_distance_px = 6.0

    if min_distance_px < 0.1:
        min_distance_px = 0.1

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
            xq = round(x * 4) / 4.0
            yq = round(y * 4) / 4.0
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
            xq = round(x * 4) / 4.0
            yq = round(y * 4) / 4.0
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
            xq = round(x * 4) / 4.0
            yq = round(y * 4) / 4.0
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
            xq = round(x * 4) / 4.0
            yq = round(y * 4) / 4.0
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

    def run_detect(thr, allow_param=True):
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
        added = len(new_tracks)
        removed_prev = _remove_overlapping(prev_tracks, new_tracks, context.scene.frame_current)
        # Nach Entfernen, filtere verbliebene "neue" erneut (da einige gelöscht wurden)
        after_tracks2 = list(clip.tracking.tracks)
        new_tracks_remaining = [t for t in after_tracks2 if id(t) not in prev_ids]
        removed_new = _remove_within_new(new_tracks_remaining, context.scene.frame_current)
        _d(f"Pass thr={thr:.6f} added={added} removed_prev={removed_prev} removed_new={removed_new} min_dist={min_distance_px} overlap_thr={overlap_threshold} use_overlap={use_overlap}")
        return added, removed_prev, removed_new, note

    try:
        try:
            # Prefer temp_override
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    added, removed_prev, removed_new, note = run_detect(current, allow_param=False)
                    per_pass.append((current, added, removed_prev + removed_new, note or 'kein threshold Param'))
                    passes = 1
                else:
                    while current >= min_threshold and passes < max_passes:
                        added, removed_prev, removed_new, note = run_detect(current, allow_param=True)
                        per_pass.append((current, added, removed_prev + removed_new, note))
                        passes += 1
                        current *= factor
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            if not has_threshold:
                added, removed_prev, removed_new, note = run_detect(current, allow_param=False)
                per_pass.append((current, added, removed_prev + removed_new, (note or '') + ' fallback ohne threshold'))
                passes = 1
            else:
                while current >= min_threshold and passes < max_passes:
                    added, removed_prev, removed_new, note = run_detect(current, allow_param=True)
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

    _d(f"Fertig: passes={passes} total_added={total_added} total_removed={total_removed} min_distance={min_distance_px}")
    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'total_removed': total_removed,
        'per_pass': per_pass,
        'min_distance_px': min_distance_px,
    }
