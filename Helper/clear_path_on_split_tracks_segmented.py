# Helper/clear_path_on_split_tracks_segmented.py
import bpy
from .process_marker_path import get_track_segments


def _select_only(space, track):
    """Nur den angegebenen Track selektieren."""
    tracks = space.clip.tracking.tracks
    for t in tracks:
        t.select = False
    if track:
        track.select = True


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


def _duplicate_once_invoke(context, area, region, space, source_track):
    """
    Dupliziert genau EINEN Track via Copy/Paste mit INVOKE_DEFAULT
    (sichtbares UI-Verhalten). Gibt die neue Track-Instanz zurück oder None.
    Erwartung: Wir isolieren die Selektion hier selbst.
    """
    tracks = space.clip.tracking.tracks
    with context.temp_override(area=area, region=region, space_data=space):
        # Selektion isolieren
        for t in tracks:
            t.select = False
        source_track.select = True

        before = {t.name for t in tracks}
        # UI-Feedback beim Kopieren/Einfügen
        try:
            bpy.ops.clip.copy_tracks('INVOKE_DEFAULT')
            _ui_blink(context, swap=True)
            bpy.ops.clip.paste_tracks('INVOKE_DEFAULT')
            _ui_blink(context, swap=True)
        except Exception:
            return None

        after = {t.name for t in tracks}
        new_names = list(after - before)
        if not new_names:
            return None

        # Normalerweise wird genau ein Track erzeugt
        for t in tracks:
            if t.name in new_names:
                return t
    return None


def _trim_to_segment_invoke(context, area, region, space, track, seg_start, seg_end):
    """
    Lässt im angegebenen Track nur das Segment [seg_start, seg_end] stehen.
    UI-Feedback per INVOKE_DEFAULT-Operatoren.
    Vorgehen:
      1) Bei seg_end: action='REMAINED' → alles NACH seg_end löschen
      2) Bei seg_start: action='UPTO'    → alles VOR  seg_start löschen
    """
    if not track:
        return
    tracks = space.clip.tracking.tracks

    with context.temp_override(area=area, region=region, space_data=space):
        # Selektion isolieren
        for t in tracks:
            t.select = False
        track.select = True

        # 1) Nach Segment-Ende löschen
        try:
            context.scene.frame_set(seg_end)
            bpy.ops.clip.clear_track_path('INVOKE_DEFAULT',
                                          action='REMAINED',
                                          clear_active=False)
            _ui_blink(context, swap=True)
        except Exception:
            pass

        # 2) Vor Segment-Beginn löschen
        try:
            context.scene.frame_set(seg_start)
            bpy.ops.clip.clear_track_path('INVOKE_DEFAULT',
                                          action='UPTO',
                                          clear_active=False)
            _ui_blink(context, swap=True)
        except Exception:
            pass


def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    """
    Segment-basierter Split je Original-Track mit sichtbarem UI-Feedback:
      - Für k Segmente werden k Ziel-Tracks erzeugt (Original + k-1 Duplikate).
      - Duplikation via INVOKE_DEFAULT (Copy/Paste) → sichtbar.
      - Pro Ziel-Track bleibt genau EIN Segment bestehen (Trim via INVOKE_DEFAULT).
    Hinweis: 'new_tracks' wird aus Kompatibilität akzeptiert, hier aber nicht benötigt.
    """
    if not space or not getattr(space, "clip", None):
        return

    tracks = space.clip.tracking.tracks

    # Arbeitskontext sichern
    with context.temp_override(area=area, region=region, space_data=space):
        for orig in list(original_tracks):
            # Segmente ermitteln
            try:
                segs = get_track_segments(orig)
            except Exception:
                segs = []

            if not segs:
                continue

            # Ziel-Container: Original + Duplikate (k-1)
            k = len(segs)
            targets = [orig]

            # Dynamisch duplizieren, bis Anzahl == k
            while len(targets) < k:
                dup = _duplicate_once_invoke(context, area, region, space, orig)
                if dup is None:
                    # Duplikation gescheitert → weniger Segmente werden separiert
                    break
                targets.append(dup)

            # Jedem verfügbaren Ziel genau ein Segment zuordnen
            limit = min(len(targets), len(segs))
            for idx in range(limit):
                t = targets[idx]
                seg_start, seg_end = segs[idx]
                _trim_to_segment_invoke(context, area, region, space, t, seg_start, seg_end)

        # Abschließende, schlanke UI-Aktualisierung
        _ui_blink(context, swap=True)
