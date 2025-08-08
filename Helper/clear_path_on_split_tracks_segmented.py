# Helper/clear_path_on_split_tracks_segmented.py
import time
import bpy
from .process_marker_path import get_track_segments


# ---------- kleine Utilities (modular / synchronisationsfähig) ----------

def _ui_blink(context, *, swap=False):
    """Gezielte UI-Aktualisierung: optional mit Swap für sichtbares Feedback."""
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP' if swap else 'DRAW', iterations=1)
    except Exception:
        pass
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


def _select_only(space, track):
    """Nur den angegebenen Track selektieren (isoliert)."""
    tracks = space.clip.tracking.tracks
    for t in tracks:
        t.select = False
    if track:
        track.select = True


def _wait_until(predicate, timeout=1.5, poll=0.02, pulse=None):
    """
    Blockiert bis predicate() True liefert oder timeout erreicht ist.
    Optional: pulse() pro Poll zur UI-Beat (Draw).
    """
    t0 = time.time()
    while (time.time() - t0) < timeout:
        try:
            if predicate():
                return True
        except Exception:
            # ignorieren, erneut pollen
            pass
        if pulse:
            pulse()
        time.sleep(poll)
    return False


# ---------- Duplikation (INVOCATION + Ack + EXEC-Fallback) ----------

def _duplicate_once_invoke(context, area, region, space, source_track):
    """
    Dupliziert genau EINEN Track via Copy/Paste mit INVOKE_DEFAULT (sichtbar).
    Striktes Sequencing: Warte auf Ack (neuer Track sichtbar). Fallback: EXEC_DEFAULT.
    Gibt die neue Track-Instanz zurück oder None.
    """
    tracks = space.clip.tracking.tracks
    with context.temp_override(area=area, region=region, space_data=space):
        # Selektion isolieren + active setzen (einige Ops adressieren 'active')
        for t in tracks:
            t.select = False
        source_track.select = True
        try:
            space.clip.tracking.tracks.active = source_track
        except Exception:
            pass

        before = {t.name for t in tracks}

        # 1) INVOKE-Pfad (sichtbar)
        try:
            bpy.ops.clip.copy_tracks('INVOKE_DEFAULT')
            _ui_blink(context, swap=True)
            bpy.ops.clip.paste_tracks('INVOKE_DEFAULT')
            _ui_blink(context, swap=True)
        except Exception:
            return None

        # Ack: es muss ein neuer Name auftauchen
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
