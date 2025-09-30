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

    def marker_center_px(track, frame, width, height):
        if frame is None:
            return None
        # Find marker for frame
        m = None
        for mk in track.markers:
            if mk.frame == frame:
                m = mk
                break
        if m is None:
            return None
        return (m.co[0] * width, m.co[1] * height)

    def collect_existing_centers(frame):
        centers = []
        if not clip:
            return centers
        w, h = clip.size
        for t in clip.tracking.tracks:
            c = marker_center_px(t, frame, w, h)
            if c:
                centers.append((t.name, c))
        return centers

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
                existing_centers = collect_existing_centers(frame)
                existing_names = {name for name, _ in existing_centers}

                if not has_threshold:
                    added_raw, note = run_detect(current, allow_param=False)
                    removed = 0
                    if added_raw > 0 and clip:
                        # Filter overlaps
                        w, h = clip.size
                        new_tracks = [t for t in clip.tracking.tracks if t.name not in existing_names]
                        for t in list(new_tracks):
                            c = marker_center_px(t, frame, w, h)
                            if not c:
                                continue
                            for _, old_c in existing_centers:
                                dx = c[0] - old_c[0]
                                dy = c[1] - old_c[1]
                                if (dx*dx + dy*dy) ** 0.5 <= overlap_pixel_threshold:
                                    clip.tracking.tracks.remove(t)
                                    removed += 1
                                    break
                    per_pass.append((current, added_raw - removed, (note or 'kein threshold Param') + (f', removed {removed}' if removed else '')))
                    passes = 1
                else:
                    while current >= min_threshold and passes < max_passes:
                        frame = current_frame()
                        existing_centers = collect_existing_centers(frame)
                        existing_names = {name for name, _ in existing_centers}
                        added_raw, note = run_detect(current, allow_param=True)
                        removed = 0
                        if added_raw > 0 and clip:
                            w, h = clip.size
                            new_tracks = [t for t in clip.tracking.tracks if t.name not in existing_names]
                            for t in list(new_tracks):
                                c = marker_center_px(t, frame, w, h)
                                if not c:
                                    continue
                                for _, old_c in existing_centers:
                                    dx = c[0] - old_c[0]
                                    dy = c[1] - old_c[1]
                                    if (dx*dx + dy*dy) ** 0.5 <= overlap_pixel_threshold:
                                        clip.tracking.tracks.remove(t)
                                        removed += 1
                                        break
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
            existing_centers = collect_existing_centers(frame)
            existing_names = {name for name, _ in existing_centers}
            if not has_threshold:
                prev = len(clip.tracking.tracks) if clip else 0
                bpy.ops.clip.detect_features(override)
                new_total = len(clip.tracking.tracks) if clip else prev
                added_raw = new_total - prev
                removed = 0
                if added_raw > 0 and clip:
                    w, h = clip.size
                    new_tracks = [t for t in clip.tracking.tracks if t.name not in existing_names]
                    for t in list(new_tracks):
                        c = marker_center_px(t, frame, w, h)
                        if not c:
                            continue
                        for _, old_c in existing_centers:
                            dx = c[0] - old_c[0]
                            dy = c[1] - old_c[1]
                            if (dx*dx + dy*dy) ** 0.5 <= overlap_pixel_threshold:
                                clip.tracking.tracks.remove(t)
                                removed += 1
                                break
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
                    new_total = len(clip.tracking.tracks) if clip else prev
                    added_raw = new_total - prev
                    removed = 0
                    if added_raw > 0 and clip:
                        w, h = clip.size
                        new_tracks = [t for t in clip.tracking.tracks if t.name not in existing_names]
                        for t in list(new_tracks):
                            c = marker_center_px(t, frame, w, h)
                            if not c:
                                continue
                            for _, old_c in existing_centers:
                                dx = c[0] - old_c[0]
                                dy = c[1] - old_c[1]
                                if (dx*dx + dy*dy) ** 0.5 <= overlap_pixel_threshold:
                                    clip.tracking.tracks.remove(t)
                                    removed += 1
                                    break
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
