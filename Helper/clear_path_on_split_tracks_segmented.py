# Helper/clear_path_on_split_tracks_segmented.py
import bpy
from .process_marker_path import get_track_segments


def _ui_blink(context, *, swap=False):
    """Dezenter UI-Refresh."""
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP' if swap else 'DRAW', iterations=1)
    except Exception:
        pass
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


def _select_only(space, track):
    """Selektion isolieren."""
    tracks = space.clip.tracking.tracks
    for t in tracks:
        t.select = False
    if track:
        track.select = True


def _duplicate_once_exec(context, area, region, space, source_track):
    """
    Dupliziert genau EINEN Track synchron (EXEC_DEFAULT).
    Rückgabe: neue Track-Instanz oder None.
    """
    tracks = space.clip.tracking.tracks
    with context.temp_override(area=area, region=region, space_data=space):
        # Selektion/Active
        for t in tracks:
            t.select = False
        source_track.select = True
        try:
            tracks.active = source_track
        except Exception:
            pass

        before = {t.name for t in tracks}
        try:
            bpy.ops.clip.copy_tracks('EXEC_DEFAULT')
            bpy.ops.clip.paste_tracks('EXEC_DEFAULT')
        except Exception:
            return None

        after = {t.name for t in tracks}
        new_names = list(after - before)
        if not new_names:
            return None

        # neue Instanz zurückgeben
        for t in tracks:
            if t.name in new_names:
                return t
    return None


def _trim_to_segment_exec(context, area, region, space, track, seg_start, seg_end):
    """
    Lässt im Track nur [seg_start, seg_end] stehen (synchron, EXEC_DEFAULT).
    Reihenfolge:
      1) REMAINED bei seg_end  (alles danach weg)
      2) UPTO    bei seg_start (alles davor weg)
    """
    if not track:
        return
    tracks = space.clip.tracking.tracks
    with context.temp_override(area=area, region=region, space_data=space):
        # nur diesen Track selektieren
        for t in tracks:
            t.select = False
        track.select = True

        # nach Ende löschen
        try:
            context.scene.frame_set(seg_end)
            bpy.ops.clip.clear_track_path('EXEC_DEFAULT',
                                          action='REMAINED',
                                          clear_active=False)
        except Exception:
            pass

        # vor Beginn löschen
        try:
            context.scene.frame_set(seg_start)
            bpy.ops.clip.clear_track_path('EXEC_DEFAULT',
                                          action='UPTO',
                                          clear_active=False)
        except Exception:
            pass

        _ui_blink(context)  # dezentes Update pro Ziel


def split_tracks_segmented_timed(context, area, region, space, original_tracks,
                                 delay_seconds=None, batch_size=None, settle_ticks=None):
    """
    SYNCHRONE Zwei-Phasen-Variante (keine Timer, keine Batches):
      Phase A: Für alle Original-Tracks mit >=2 Segmenten die benötigten Duplikate erzeugen.
      Phase B: Für jedes Segment den korrespondierenden Ziel-Track trimmen.

    Die Parameter delay_seconds/batch_size/settle_ticks werden ignoriert (Backward-compat API).
    Rückgabe: Anzahl ausgeführter Einzelschritte (Duplizieren + Trim).
    """
    if not space or not getattr(space, "clip", None):
        return 0

    # --- Jobs vorbereiten: nur Tracks mit >=2 Segmenten
    jobs = []  # [{ 'orig': Track, 'segments': [(s,e),...], 'targets': [Track] }]
    for orig in list(original_tracks):
        try:
            segs = get_track_segments(orig) or []
        except Exception:
            segs = []
        if len(segs) >= 2:
            jobs.append({
                'orig': orig,
                'segments': segs,
                'targets': [orig],                # Original als erstes Target
            })

    if not jobs:
        return 0

    steps_done = 0

    # -------- Phase A: Duplizieren (synchron)
    for job in jobs:
        segs = job['segments']
        needed = max(0, len(segs) - 1)
        for _ in range(needed):
            new = _duplicate_once_exec(context, area, region, space, job['orig'])
            if new:
                job['targets'].append(new)
                steps_done += 1
        # kleiner UI-Beat pro Job
        _ui_blink(context)

    # -------- Phase B: Trimmen (synchron)
    for job in jobs:
        segs = job['segments']
        targets = job['targets']
        # Safety: nur so viele Ziele wie Segmente existieren
        limit = min(len(segs), len(targets))
        for idx in range(limit):
            s, e = segs[idx]
            _trim_to_segment_exec(context, area, region, space, targets[idx], s, e)
            steps_done += 1
        # UI-Beat pro Job
        _ui_blink(context, swap=True)

    return steps_done
