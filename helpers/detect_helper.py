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

    def _remove_overlapping(new_track_names, old_centers, frame_current):
        if not clip or not new_track_names:
            return 0
        w, h = clip.size
        removed = 0
        min_dist_sq = min_distance_px * min_distance_px
        # Erstelle schnelle Liste ohne Namen für Distanz
        old_pts = [(ox, oy) for _n, ox, oy in old_centers]
        for tr in list(clip.tracking.tracks):
            if tr.name not in new_track_names:
                continue
            pos = _get_marker_center(tr, frame_current, w, h)
            if pos is None:
                continue
            x, y = pos
            xq = round(x * 4) / 4.0
            yq = round(y * 4) / 4.0
            for (ox, oy) in old_pts:
                dx = xq - ox
                dy = yq - oy
                if (dx * dx + dy * dy) <= min_dist_sq:
                    try:
                        clip.tracking.tracks.remove(tr)
                        removed += 1
                    except Exception:  # noqa: BLE001
                        pass
                    break
        return removed

    def run_detect(thr, allow_param=True):
        prev_names = set(tr.name for tr in clip.tracking.tracks) if clip else set()
        old_centers = _collect_track_centers(context.scene.frame_current)
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
            return 0, 0, f'Fehler detect: {e}'
        # Auswertung
        if not clip:
            return 0, 0, note
        new_names = [tr.name for tr in clip.tracking.tracks if tr.name not in prev_names]
        added = len(new_names)
        removed = _remove_overlapping(new_names, old_centers, context.scene.frame_current)
        return added, removed, note

    try:
        try:
            # Prefer temp_override
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    added, removed, note = run_detect(current, allow_param=False)
                    per_pass.append((current, added, removed, note or 'kein threshold Param'))
                    passes = 1
                else:
                    while current >= min_threshold and passes < max_passes:
                        added, removed, note = run_detect(current, allow_param=True)
                        per_pass.append((current, added, removed, note))
                        passes += 1
                        current *= factor
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            if not has_threshold:
                added, removed, note = run_detect(current, allow_param=False)
                per_pass.append((current, added, removed, (note or '') + ' fallback ohne threshold'))
                passes = 1
            else:
                while current >= min_threshold and passes < max_passes:
                    added, removed, note = run_detect(current, allow_param=True)
                    per_pass.append((current, added, removed, note + ' fallback'))
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
