# Helper/clear_path_on_split_tracks_segmented.py
import bpy
import time
from .process_marker_path import get_track_segments


def _ui_blink(context, *, swap=False):
    """Gezielter UI-Refresh (dezent)."""
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
    Gibt die neue Track-Instanz zurück oder None.
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

        _ui_blink(context)  # dezentes Update


def split_tracks_segmented_timed(context, area, region, space, original_tracks, delay_seconds=2.0):
    """
    'Alte' Methode (synchron, EXEC_DEFAULT), aber strikt sequenziert via bpy.app.timers.
    – Für k Segmente pro Original werden k-1 Duplikate erzeugt.
    – Danach wird pro Ziel-Track exakt EIN Segment stehen gelassen.
    – Jeder einzelne Schritt wird über einen Timer mit 'delay_seconds' Abstand ausgeführt.
    """
    if not space or not getattr(space, "clip", None):
        return 0

    actions = []  # Liste von Callables (ohne Argumente), die nacheinander laufen

    # Pro Original-Track Aktionskette aufbauen
    for orig in list(original_tracks):
        try:
            segs = get_track_segments(orig) or []
        except Exception:
            segs = []

        if len(segs) < 2:
            continue

        # Container, in den die Duplikate zur Laufzeit appended werden
        targets = [orig]

        # (1) Duplikations-Schritte (k-1 Stück), synchron EXEC_DEFAULT
        dup_count = len(segs) - 1

        def _make_dup_step(o=orig, tgt_list=targets):
            def _step():
                new = _duplicate_once_exec(context, area, region, space, o)
                if new:
                    tgt_list.append(new)
            return _step

        for _ in range(dup_count):
            actions.append(_make_dup_step())

        # (2) Trim-Schritte: für jedes Ziel (Original + Duplikate) das korrespondierende Segment stehen lassen
        for idx in range(len(segs)):
            s, e = segs[idx]

            def _make_trim_step(i=idx, start=s, end=e, tgt_list=targets):
                def _step():
                    if i >= len(tgt_list):  # Safety
                        return
                    _trim_to_segment_exec(context, area, region, space, tgt_list[i], start, end)
                return _step

            actions.append(_make_trim_step())

    # --- Timer-orchestrierter Ablauf -----------------------------------------
    if not actions:
        return 0

    idx = {'i': 0}  # mutable Counter im Closure

    def _runner():
        i = idx['i']
        if i >= len(actions):
            return None  # stoppt den Timer
        try:
            actions[i]()  # Schritt i ausführen (synchron)
        except Exception as ex:
            print(f"[TimedSplit] Step {i} Exception: {ex}")
        idx['i'] = i + 1
        return delay_seconds  # nächster Aufruf in delay_seconds

    # ersten Call nach kurzer Initialisierung (0.1s), danach alle delay_seconds
    try:
        bpy.app.timers.register(_runner, first_interval=0.1, persistent=False)
    except Exception as ex:
        print(f"[TimedSplit] Timer-Registrierung fehlgeschlagen: {ex}")
        return 0

    return len(actions)
