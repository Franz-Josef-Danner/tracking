"""Kompakter Helper für Multi-Pass Feature Detection mit Distanzfilter.

Funktionen / Verhalten:
 - Mehrfaches Ausführen von bpy.ops.clip.detect_features mit optionalem Threshold.
 - Threshold startet bei start_threshold und wird jedes Mal mit `factor` multipliziert
   bis < min_threshold oder max_passes erreicht.
 - pattern_size initial = max(3, round(1% der Clip-Breite)), search_size = 2 * pattern_size.
 - Vor jedem Pass Setzen (ggf. wachsendes) pattern/search in Tracking Settings.
 - Progressives Wachstum: cur_pattern_progressive *= 1.15 (fix laut Anforderung).
 - Distanzfilter: Neuer Marker (Frame) wird verworfen (delete_frame), falls Pixelabstand
   < aktuelles pattern_size zu bereits akzeptiertem Marker liegt. Leere Tracks werden gelöscht.
 - Logging aller akzeptierten & gefilterten Marker (marker_logs).
 - Rückgabe: Statistik + Logs.
"""
from __future__ import annotations

try:  # Blender Umgebung
    import bpy  # type: ignore
except ImportError:  # außerhalb Blender
    bpy = None  # type: ignore

__all__ = ["find_clip_editor_area", "get_clip_from_area", "detect_features_multipass"]


def find_clip_editor_area(context):
    if bpy is None:
        return None
    for window in context.window_manager.windows:
        scr = window.screen
        if not scr:
            continue
        area = next((a for a in scr.areas if a.type == 'CLIP_EDITOR'), None)
        if area:
            return area
    return None


def get_clip_from_area(area):
    if area is None:
        return None
    try:
        return area.spaces.active.clip
    except Exception:  # noqa: BLE001
        return None


def _get_marker_on_frame(track, frame):
    if frame is not None:
        for m in track.markers:
            if m.frame == frame:
                return m
    if track.markers:
        return track.markers[0]
    return None


def detect_features_multipass(
    context,
    start_threshold: float = 1.0,
    min_threshold: float = 0.0001,
    factor: float = 0.5,
    max_passes: int = 32,
):
    if bpy is None:
        return {"success": False, "message": "bpy nicht verfügbar"}

    area = find_clip_editor_area(context)
    if area is None:
        return {"success": False, "message": "Kein Movie Clip Editor Bereich gefunden."}
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return {"success": False, "message": "Keine WINDOW Region gefunden."}

    clip = get_clip_from_area(area)
    if clip is None:
        return {"success": False, "message": "Kein Clip aktiv."}

    # Auflösung
    w = h = None
    try:
        w, h = clip.size
        print(f"[TrackingHelper] Clip Breite (px): {w}")
    except Exception:  # noqa: BLE001
        pass

    pattern_size = max(3, int(round((w or 0) * 0.01))) if w else 16
    search_size = pattern_size * 2

    settings = getattr(clip.tracking, 'settings', None)
    old_pattern = getattr(settings, 'default_pattern_size', None) if settings and hasattr(settings, 'default_pattern_size') else None
    old_search = getattr(settings, 'default_search_size', None) if settings and hasattr(settings, 'default_search_size') else None
    if settings is not None:
        try:
            if hasattr(settings, 'default_pattern_size'):
                settings.default_pattern_size = pattern_size
            if hasattr(settings, 'default_search_size'):
                settings.default_search_size = search_size
            print(f"[TrackingHelper] Set pattern_size={pattern_size} search_size={search_size}")
        except Exception:  # noqa: BLE001
            pass

    # Threshold-Unterstützung prüfen
    has_threshold = False
    try:
        rna = bpy.ops.clip.detect_features.get_rna_type()
        has_threshold = 'threshold' in rna.properties.keys()
    except Exception:  # noqa: BLE001
        has_threshold = False

    base_track_ids = {id(t) for t in clip.tracking.tracks}
    accepted_positions: list[tuple[float, float]] = []
    cur_frame_init = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
    if w and h:
        for t in clip.tracking.tracks:
            m = _get_marker_on_frame(t, cur_frame_init)
            if m is not None:
                co = m.co
                accepted_positions.append((co[0] * w, co[1] * h))

    per_pass: list[tuple[float, int, str]] = []
    marker_logs: list[dict] = []
    removed_markers = 0
    passes = 0
    thr = start_threshold
    cur_pattern_progressive = float(pattern_size)

    def apply_sizes(pat: float):
        nonlocal pattern_size, search_size
        p = max(3, int(round(pat)))
        s = p * 2
        if settings is not None:
            try:
                if hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = p
                if hasattr(settings, 'default_search_size'):
                    settings.default_search_size = s
            except Exception:  # noqa: BLE001
                pass
        pattern_size, search_size = p, s

    def run_detect(current_thr: float):
        prev = len(clip.tracking.tracks)
        note = ''
        try:
            if has_threshold:
                bpy.ops.clip.detect_features(threshold=current_thr)
            else:
                bpy.ops.clip.detect_features()
                note = 'no-threshold'
        except TypeError:
            bpy.ops.clip.detect_features()
            note = 'TypeError->no-threshold'
        except Exception as e:  # noqa: BLE001
            return 0, f'error:{e}'
        return len(clip.tracking.tracks) - prev, note

    def process_new(pass_index: int, current_thr: float):
        nonlocal removed_markers
        new_tracks = [t for t in clip.tracking.tracks if id(t) not in base_track_ids]
        if not new_tracks:
            return 0
        cur_frame = bpy.context.scene.frame_current if bpy.context and bpy.context.scene else None
        accepted_this_pass = 0
        limit = float(pattern_size)
        for t in new_tracks:
            m = _get_marker_on_frame(t, cur_frame)
            frame_used = None
            pos_norm = None
            pos_px = None
            if m is not None:
                frame_used = m.frame
                pos_norm = tuple(m.co)
                if w and h:
                    pos_px = (pos_norm[0] * w, pos_norm[1] * h)
            too_close = False
            if pos_px and accepted_positions:
                mx, my = pos_px
                for (ax, ay) in accepted_positions:
                    dx = mx - ax
                    dy = my - ay
                    if (dx * dx + dy * dy) ** 0.5 < limit:
                        too_close = True
                        break
            if too_close and frame_used is not None:
                try:
                    t.markers.delete_frame(frame_used)
                    removed_markers += 1
                    print(f"[TrackingHelper] Pass {pass_index} thr {current_thr:.5f} MARKER gelöscht track='{t.name}' frame={frame_used} pos_px={pos_px} (dist < {limit})")
                    marker_logs.append({
                        'pass': pass_index,
                        'threshold': current_thr,
                        'track_name': t.name,
                        'frame': frame_used,
                        'pos_norm': pos_norm,
                        'pos_px': pos_px,
                        'pattern': pattern_size,
                        'search': search_size,
                        'filtered': True,
                        'reason': f'dist < pattern_size ({limit})',
                    })
                    if len(t.markers) == 0:
                        try:
                            clip.tracking.tracks.remove(t)
                        except Exception:  # noqa: BLE001
                            pass
                    continue
                except Exception:  # noqa: BLE001
                    pass
            if pos_px:
                accepted_positions.append(pos_px)
            accepted_this_pass += 1
            marker_logs.append({
                'pass': pass_index,
                'threshold': current_thr,
                'track_name': t.name,
                'frame': frame_used,
                'pos_norm': pos_norm,
                'pos_px': pos_px,
                'pattern': pattern_size,
                'search': search_size,
                'filtered': False,
            })
        base_track_ids.update({id(t) for t in new_tracks})
        return accepted_this_pass

    # Haupt-Loop
    try:
        try:
            with context.temp_override(area=area, region=region):
                while thr >= min_threshold and passes < max_passes:
                    apply_sizes(cur_pattern_progressive)
                    added_raw, note = run_detect(thr)
                    process_new(passes + 1, thr)
                    per_pass.append((thr, added_raw, note))
                    passes += 1
                    thr *= factor
                    cur_pattern_progressive *= 1.15  # nicht ändern
        except AttributeError:  # fallback ohne temp_override
            while thr >= min_threshold and passes < max_passes:
                apply_sizes(cur_pattern_progressive)
                added_raw, note = run_detect(thr)
                process_new(passes + 1, thr)
                per_pass.append((thr, added_raw, note))
                passes += 1
                thr *= factor
                cur_pattern_progressive *= 1.5  # aggressiver im Fallback
    except Exception as e:  # noqa: BLE001
        return {
            'success': False,
            'message': f'Fehler: {e}',
            'passes': passes,
            'total_added': -1,
            'per_pass': per_pass,
            'pattern_size': pattern_size,
            'search_size': search_size,
            'marker_logs': marker_logs,
            'removed': removed_markers,
        }
    finally:
        if settings is not None:
            try:
                if old_pattern is not None and hasattr(settings, 'default_pattern_size'):
                    settings.default_pattern_size = old_pattern
                if old_search is not None and hasattr(settings, 'default_search_size'):
                    settings.default_search_size = old_search
            except Exception:  # noqa: BLE001
                pass

    accepted_count = sum(1 for m in marker_logs if not m.get('filtered'))
    total_added_est = accepted_count + removed_markers

    return {
        'success': True,
        'message': 'OK',
        'passes': passes,
        'total_added': total_added_est,
        'per_pass': per_pass,
        'pattern_size': pattern_size,
        'search_size': search_size,
        'marker_logs': marker_logs,
        'removed': removed_markers,
    }
