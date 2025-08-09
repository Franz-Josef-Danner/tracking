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
        # Achtung: targets wird zur Laufzeit bereits gefüllt sein, wenn diese Steps laufen.
        for idx in range(len(segs)):
            s, e = segs[idx]

            def _make_trim_step(i=idx, start=s, end=e, tgt_list=targets):
                def _step():
                    # Safety: falls noch nicht genug Duplikate existieren, no-op
                    if i >= len(tgt_list):
                        return
                    _trim_to_segment_exec(context, area, region, space, tgt_list[i], start, end)
                return _step

            actions.append(_make_trim_step())

    # --- Timer-orchestrierter Ablauf -----------------------------------------
    # Jeder Schritt wird um 'delay_seconds' später ausgeführt als der vorherige.

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
        def _has_new_track():
            after = {t.name for t in tracks}
            return len(after - before) > 0

        ok = _wait_until(_has_new_track, timeout=1.0, poll=0.02,
                         pulse=lambda: _ui_blink(context, swap=False))

        # 2) EXEC-Fallback: falls INVOKE-Ack nicht kam
        if not ok:
            try:
                bpy.ops.clip.paste_tracks('EXEC_DEFAULT')
                ok = _wait_until(_has_new_track, timeout=0.5, poll=0.02,
                                 pulse=lambda: _ui_blink(context, swap=False))
            except Exception:
                return None

        if not ok:
            return None

        # Rückgabe des wirklich neuen Tracks
        after = {t.name for t in tracks}
        new_names = list(after - before)
        for t in tracks:
            if t.name in new_names:
                return t

    return None


# ---------- Trimmen auf exakt ein Segment (INVOCATION + Ack) ----------

def _trim_to_segment_invoke(context, area, region, space, track, seg_start, seg_end):
    """
    Lässt im angegebenen Track nur das Segment [seg_start, seg_end] stehen.
    UI-sichtbar mit INVOKE_DEFAULT. Sequenziert durch Acks nach jedem Schritt.
    Reihenfolge:
      1) Bei seg_end → action='REMAINED' (alles nach seg_end löschen)
      2) Bei seg_start → action='UPTO'   (alles vor  seg_start löschen)
    Ack: get_track_segments(track) == 1 und deckt [seg_start, seg_end] (tolerant).
    """
    if not track:
        return False

    tracks = space.clip.tracking.tracks
    with context.temp_override(area=area, region=region, space_data=space):
        # Selektion isolieren
        for t in tracks:
            t.select = False
        track.select = True

        # Schritt 1: nach Ende löschen
        try:
            context.scene.frame_set(seg_end)
            bpy.ops.clip.clear_track_path('INVOKE_DEFAULT',
                                          action='REMAINED',
                                          clear_active=False)
            _ui_blink(context, swap=True)
        except Exception:
            pass

        # Minimalsperre, damit INVOKE seinen Lauf nimmt
        _wait_until(lambda: True, timeout=0.05, poll=0.02)

        # Schritt 2: vor Beginn löschen
        try:
            context.scene.frame_set(seg_start)
            bpy.ops.clip.clear_track_path('INVOKE_DEFAULT',
                                          action='UPTO',
                                          clear_active=False)
            _ui_blink(context, swap=True)
        except Exception:
            pass

        # Ack: genau ein Segment und es deckt [seg_start, seg_end] ~ ab
        def _trim_ack():
            segs = []
            try:
                segs = get_track_segments(track) or []
            except Exception:
                return False
            if len(segs) != 1:
                return False
            s0, e0 = segs[0]
            # Toleranz: 1 Frame, weil Marker-Enden durch Ops off-by-one sein können
            return (s0 >= seg_start - 1) and (e0 <= seg_end + 1)

        ok = _wait_until(_trim_ack, timeout=1.0, poll=0.02,
                         pulse=lambda: _ui_blink(context, swap=False))
        return ok


# ---------- Öffentliche API: Segmentierter Split pro Original-Track ----------

def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    """
    Segment-basierter Split je Original-Track mit strikt sequenziertem Ablauf:
      - Für k Segmente werden k Ziel-Tracks erzeugt (Original + k−1 Duplikate).
      - Duplikation via INVOKE_DEFAULT (sichtbar) + Ack-Wait → deterministisch.
      - Pro Ziel-Track bleibt genau EIN Segment bestehen (Trim via INVOKE_DEFAULT) + Ack-Wait.
    Hinweis: 'new_tracks' ist für Abwärtskompatibilität vorhanden, wird hier aber nicht genutzt.
    """
    if not space or not getattr(space, "clip", None):
        return

    tracks = space.clip.tracking.tracks
    with context.temp_override(area=area, region=region, space_data=space):
        for orig in list(original_tracks):
            # Segmente für diesen Original-Track holen
            try:
                segs = get_track_segments(orig) or []
            except Exception:
                segs = []

            if not segs:
                continue

            # Zielcontainer: Original + (k−1) Duplikate
            k = len(segs)
            targets = [orig]

            # Dupliziere deterministisch so lange, bis wir k Ziele haben
            while len(targets) < k:
                dup = _duplicate_once_invoke(context, area, region, space, orig)
                if dup is None:
                    # Duplikation scheiterte → weniger Segmente werden separiert
                    break
                targets.append(dup)

            # Trimmen: jedem verfügbaren Ziel genau ein Segment zuordnen
            limit = min(len(targets), len(segs))
            for idx in range(limit):
                t = targets[idx]
                seg_start, seg_end = segs[idx]
                _select_only(space, t)
                _ = _trim_to_segment_invoke(context, area, region, space, t, seg_start, seg_end)

        # Abschluss-Refresh (sichtbar, aber nur einmal)
        _ui_blink(context, swap=True)
