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
    overlap_pixel_threshold=6,
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

    per_pass = []
    passes = 0
    current = start_threshold

    def current_frame():
        try:
            return context.scene.frame_current
        except Exception:  # noqa: BLE001
            return None

    def marker_and_bbox_px(track, frame, width, height):
        """Return (center(x,y), (xmin,ymin,xmax,ymax)) in pixels for marker at frame."""
        if frame is None:
            return None, None
        marker = None
        for mk in track.markers:
            if mk.frame == frame:
                marker = mk
                break
        if marker is None:
            return None, None
        cx = marker.co[0] * width
        cy = marker.co[1] * height
        # pattern_corners are offsets relative to center in normalized coords
        xs = []
        ys = []
        try:
            for ox, oy in marker.pattern_corners:
                xs.append((marker.co[0] + ox) * width)
                ys.append((marker.co[1] + oy) * height)
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
        except Exception:  # noqa: BLE001
            # Fallback: small box around center
            pad = 4
            xmin = cx - pad
            xmax = cx + pad
            ymin = cy - pad
            ymax = cy + pad
        return (cx, cy), (xmin, ymin, xmax, ymax)

    def collect_existing(track_list, frame):
        data = []
        if not clip:
            return data
        w, h = clip.size
        for t in track_list:
            c, bb = marker_and_bbox_px(t, frame, w, h)
            if c:
                data.append((t, c, bb))
        return data

    def is_overlap(new_c, new_bb, existing_items):
        nx, ny = new_c
        nbb = new_bb
        for _t, (ex, ey), ebb in existing_items:
            # Distance check
            dx = nx - ex
            dy = ny - ey
            if (dx * dx + dy * dy) ** 0.5 <= overlap_pixel_threshold:
                return True
            # Bounding box intersection / containment
            if nbb and ebb:
                nxmin, nymin, nxmax, nymax = nbb
                exmin, eymin, exmax, eymax = ebb
                # expand existing box by threshold as margin
                exmin -= overlap_pixel_threshold
                eymin -= overlap_pixel_threshold
                exmax += overlap_pixel_threshold
                eymax += overlap_pixel_threshold
                # center inside expanded existing box
                if exmin <= nx <= exmax and eymin <= ny <= eymax:
                    return True
                # Overlap of rectangles (not strictly needed but adds robustness)
                if not (nxmax < exmin or exmax < nxmin or nymax < eymin or eymax < nymin):
                    # If overlapping heavily (intersection area vs smaller area > 0.6) -> treat as overlap
                    ixmin = max(nxmin, exmin)
                    iymin = max(nymin, eymin)
                    ixmax = min(nxmax, exmax)
                    iymax = min(nymax, eymax)
                    if ixmax > ixmin and iymax > iymin:
                        inter = (ixmax - ixmin) * (iymax - iymin)
                        narea = (nxmax - nxmin) * (nymax - nymin)
                        earea = (exmax - exmin) * (eymax - eymin)
                        smaller = min(narea, earea)
                        if smaller > 0 and inter / smaller > 0.6:
                            return True
        return False

    def run_detect(thr, allow_param=True):
        prev = len(clip.tracking.tracks) if clip else 0
        note = ''
        try:
            if has_threshold and allow_param:
                bpy.ops.clip.detect_features(threshold=thr)
            else:
                bpy.ops.clip.detect_features()
                if allow_param and not has_threshold:
                    note = 'threshold nicht unterstützt'
        except TypeError:
            # Versuche ohne Parameter
            bpy.ops.clip.detect_features()
            note = 'TypeError threshold'
        new_total = len(clip.tracking.tracks) if clip else prev
        added_raw = new_total - prev
        return added_raw, note

    try:
        try:
            # Prefer temp_override
            with context.temp_override(area=area, region=region):
                frame = current_frame()
                existing_tracks_snapshot = list(clip.tracking.tracks) if clip else []
                existing_items = collect_existing(existing_tracks_snapshot, frame)
                existing_ids = {id(t) for t in existing_tracks_snapshot}

                if not has_threshold:
                    added_raw, note = run_detect(current, allow_param=False)
                    removed = 0
                    if added_raw > 0 and clip:
                        w, h = clip.size
                        # Identify truly new tracks by object identity
                        new_tracks = [t for t in clip.tracking.tracks if id(t) not in existing_ids]
                        for t in list(new_tracks):
                            c, bb = marker_and_bbox_px(t, frame, w, h)
                            if not c:
                                continue
                            if is_overlap(c, bb, existing_items):
                                clip.tracking.tracks.remove(t)
                                removed += 1
                    per_pass.append((current, added_raw - removed, (note or 'kein threshold Param') + (f', removed {removed}' if removed else '')))
                    passes = 1
                else:
                    while current >= min_threshold and passes < max_passes:
                        frame = current_frame()
                        existing_tracks_snapshot = list(clip.tracking.tracks) if clip else []
                        existing_items = collect_existing(existing_tracks_snapshot, frame)
                        existing_ids = {id(t) for t in existing_tracks_snapshot}
                        added_raw, note = run_detect(current, allow_param=True)
                        removed = 0
                        if added_raw > 0 and clip:
                            w, h = clip.size
                            new_tracks = [t for t in clip.tracking.tracks if id(t) not in existing_ids]
                            for t in list(new_tracks):
                                c, bb = marker_and_bbox_px(t, frame, w, h)
                                if not c:
                                    continue
                                if is_overlap(c, bb, existing_items):
                                    clip.tracking.tracks.remove(t)
                                    removed += 1
                        kept = added_raw - removed
                        per_pass.append((current, kept, note + (f', removed {removed}' if removed else '')))
                        passes += 1
                        current *= factor
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            frame = current_frame()
            existing_tracks_snapshot = list(clip.tracking.tracks) if clip else []
            existing_items = collect_existing(existing_tracks_snapshot, frame)
            existing_ids = {id(t) for t in existing_tracks_snapshot}
            if not has_threshold:
                prev = len(clip.tracking.tracks) if clip else 0
                bpy.ops.clip.detect_features(override)
                new_total = len(clip.tracking.tracks) if clip else prev
                added_raw = new_total - prev
                removed = 0
                if added_raw > 0 and clip:
                    w, h = clip.size
                    new_tracks = [t for t in clip.tracking.tracks if id(t) not in existing_ids]
                    for t in list(new_tracks):
                        c, bb = marker_and_bbox_px(t, frame, w, h)
                        if not c:
                            continue
                        if is_overlap(c, bb, existing_items):
                            clip.tracking.tracks.remove(t)
                            removed += 1
                per_pass.append((current, added_raw - removed, f'fallback ohne threshold, removed {removed}' if removed else 'fallback ohne threshold'))
                passes = 1
            else:
                while current >= min_threshold and passes < max_passes:
                    prev = len(clip.tracking.tracks) if clip else 0
                    try:
                        bpy.ops.clip.detect_features(override, threshold=current)
                    except TypeError:
                        bpy.ops.clip.detect_features(override)
                        per_pass.append((current, 0, 'fallback threshold TypeError'))
                        break
                    # snapshot before filtering
                    frame = current_frame()
                    existing_tracks_snapshot = [t for t in clip.tracking.tracks if id(t) < 0]  # dummy to keep variable defined
                    # Reconstruct existing baseline for this pass: those before prev count not tracked easily here; approximate by previous iteration's total minus new
                    # Simpler: treat all previous tracks as existing_ids (cache outside loop better for clarity, omitted for fallback simplicity)
                    new_total = len(clip.tracking.tracks) if clip else prev
                    added_raw = new_total - prev
                    removed = 0
                    if added_raw > 0 and clip:
                        # Build existing items by taking first prev tracks (order stable)
                        existing_tracks_snapshot = clip.tracking.tracks[:prev]
                        existing_items = collect_existing(existing_tracks_snapshot, frame)
                        existing_ids = {id(t) for t in existing_tracks_snapshot}
                        w, h = clip.size
                        new_tracks = [t for t in clip.tracking.tracks if id(t) not in existing_ids]
                        for t in list(new_tracks):
                            c, bb = marker_and_bbox_px(t, frame, w, h)
                            if not c:
                                continue
                            if is_overlap(c, bb, existing_items):
                                clip.tracking.tracks.remove(t)
                                removed += 1
                    per_pass.append((current, added_raw - removed, 'fallback' + (f', removed {removed}' if removed else '')))
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

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'per_pass': per_pass
    }
