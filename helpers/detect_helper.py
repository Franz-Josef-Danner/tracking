try:  # Blender Umgebung
    import bpy  # type: ignore
except ImportError:  # außerhalb Blender
    bpy = None  # type: ignore


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


def detect_features_multipass(context, start_threshold=1.0, min_threshold=0.0001, factor=0.5, max_passes=32):
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
            print(f"[TrackingHelper] Clip Breite (px): {w}")
            # Berechnung gemäß Anforderung:
            # pattern_size = horizontale Auflösung * 0.01
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
                print(f"[TrackingHelper] Set pattern_size={pattern_size}, search_size={search_size}")
        except Exception:  # noqa: BLE001
            pass
    tracks_before = len(clip.tracking.tracks) if clip else -1

    # Prüfen ob threshold unterstützt wird
    has_threshold = False
    if bpy is not None:
        try:
            rna = bpy.ops.clip.detect_features.get_rna_type()
            has_threshold = 'threshold' in rna.properties.keys()
        except Exception:  # noqa: BLE001
            has_threshold = False

    per_pass = []
    passes = 0
    current = start_threshold

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
            # für Rückgabe aktualisieren (letzte Werte)
            nonlocal pattern_size, search_size
            pattern_size = p
            search_size = s
        except Exception:  # noqa: BLE001
            pass

    def run_detect(thr, allow_param=True, pass_index=0):
        prev_count = len(clip.tracking.tracks) if (clip and bpy is not None) else 0
        prev_ids = set()
        if clip and bpy is not None:
            prev_ids = {id(t) for t in clip.tracking.tracks}
        note = ''
        try:
            if bpy is None:
                return 0, 'kein bpy (Entwicklungsumgebung)'
            if has_threshold and allow_param:
                bpy.ops.clip.detect_features(threshold=thr)
            else:
                bpy.ops.clip.detect_features()
                if allow_param and not has_threshold:
                    note = 'threshold nicht unterstützt'
        except TypeError:
            # Versuche ohne Parameter
            if bpy is not None:
                bpy.ops.clip.detect_features()
            note = 'TypeError threshold'
        new_total = len(clip.tracking.tracks) if (clip and bpy is not None) else prev_count
        added = new_total - prev_count
        # Logging neuer Marker / Tracks
        if added > 0 and clip and bpy is not None:
            cur_frame = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
            for t in clip.tracking.tracks:
                if id(t) not in prev_ids:
                    marker_co_norm = None
                    marker_px = None
                    try:
                        marker = None
                        if cur_frame is not None:
                            # Suche Marker dieses Frames
                            for m in t.markers:
                                if m.frame == cur_frame:
                                    marker = m
                                    break
                        if marker is None and len(t.markers) > 0:
                            marker = t.markers[0]
                        if marker is not None:
                            marker_co_norm = marker.co
                            if w is not None and h is not None:
                                marker_px = (marker_co_norm[0] * w, marker_co_norm[1] * h)
                    except Exception:  # noqa: BLE001
                        pass
                    print(
                        f"[TrackingHelper] Pass {pass_index} thr {thr:.5f} NEUER TRACK '{t.name}' "
                        f"pos_norm={marker_co_norm} pos_px={marker_px} pattern={pattern_size} search={search_size}"
                    )
        return added, note

    try:
        try:
            # Prefer temp_override
            if bpy is None:
                raise RuntimeError('bpy nicht verfügbar')
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    # Set sizes für diesen Pass
                    apply_sizes(pattern_size)
                    added, note = run_detect(current, allow_param=False, pass_index=passes + 1)
                    per_pass.append((current, added, note or 'kein threshold Param'))
                    passes = 1
                else:
                    cur_pattern_progressive = float(pattern_size) if pattern_size else None
                    while current >= min_threshold and passes < max_passes:
                        if cur_pattern_progressive is not None:
                            apply_sizes(cur_pattern_progressive)
                        added, note = run_detect(current, allow_param=True, pass_index=passes + 1)
                        per_pass.append((current, added, note))
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
                prev = len(clip.tracking.tracks) if clip else 0
                bpy.ops.clip.detect_features(override)
                new_total = len(clip.tracking.tracks) if clip else prev
                added = new_total - prev
                # Log neue Tracks (Fallback) – vereinfachtes Logging ohne Koordinaten-Berechnung erneut
                per_pass.append((current, added, 'fallback ohne threshold'))
                passes = 1
            else:
                cur_pattern_progressive = float(pattern_size) if pattern_size else None
                while current >= min_threshold and passes < max_passes:
                    if cur_pattern_progressive is not None:
                        apply_sizes(cur_pattern_progressive)
                    prev = len(clip.tracking.tracks) if clip else 0
                    try:
                        bpy.ops.clip.detect_features(override, threshold=current)
                    except TypeError:
                        bpy.ops.clip.detect_features(override)
                        per_pass.append((current, 0, 'fallback threshold TypeError'))
                        break
                    new_total = len(clip.tracking.tracks) if clip else prev
                    added = new_total - prev
                    per_pass.append((current, added, 'fallback'))
                    passes += 1
                    current *= factor
                    if cur_pattern_progressive is not None:
                        cur_pattern_progressive *= 1.5
    except Exception as e:  # noqa: BLE001
        return {
            'success': False,
            'message': f'Fehler: {e}',
            'passes': passes,
            'total_added': -1,
            'per_pass': per_pass,
            'pattern_size': pattern_size,
            'search_size': search_size
        }
    finally:
        # Ursprüngliche Werte wiederherstellen
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

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added,
        'per_pass': per_pass,
        'pattern_size': pattern_size,
        'search_size': search_size
    }
