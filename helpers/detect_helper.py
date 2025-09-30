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
        to_delete = []
        for tr in new_tracks:
            pos = _get_marker_center(tr, frame_current, w, h)
            if pos is None:
                continue
            x, y = pos
            xq = round(x * 4) / 4.0
            yq = round(y * 4) / 4.0
            for _tr_old, ox, oy in prev_centers:
                dx = xq - ox
                dy = yq - oy
                if (dx * dx + dy * dy) <= min_dist_sq:
                    to_delete.append(tr)
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
                if (dx * dx + dy * dy) <= min_dist_sq:
                    # Delete this duplicate
                    try:
                        clip.tracking.tracks.remove(tr)
                        removed += 1
                    except Exception:  # noqa: BLE001
                        pass
                    duplicate = True
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
        if debug:
            print(f"[TrackingDetect] Thr {thr:.6f} added={added} removed_prev={removed_prev} removed_new={removed_new}")
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

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'total_removed': total_removed,
        'per_pass': per_pass,
        'min_distance_px': min_distance_px,
    }
