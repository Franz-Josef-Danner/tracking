# Helper/clear_path_on_split_tracks_segmented.py
import bpy
import time
from .process_marker_path import get_track_segments


def _select_only(space, track):
    """Nur den angegebenen Track selektieren."""
    tracks = space.clip.tracking.tracks
    for t in tracks:
        t.select = False
    track.select = True


def _duplicate_once(context, area, region, space, source_track):
    """
    Dupliziert exakt EINEN Track (source_track) per Copy/Paste und gibt den neuen Track zurück.
    Erwartung: Vor dem Aufruf ist nur source_track selektiert (oder wir setzen es hier).
    """
    tracks = space.clip.tracking.tracks
    with context.temp_override(area=area, region=region, space_data=space):
        # Selektion auf den Source-Track beschränken
        for t in tracks:
            t.select = False
        source_track.select = True

        before = {t.name for t in tracks}
        try:
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
        except Exception:
            # Falls Copy/Paste fehlschlägt → None
            return None

        after = {t.name for t in tracks}
        new_names = list(after - before)
        # Normalerweise kommt genau ein neuer Name zurück
        if not new_names:
            return None
        # Hole das neue Track-Objekt
        for t in tracks:
            if t.name in new_names:
                return t
    return None


def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    """
    Segment-basierter Split je Original-Track:
      - Ermittelt für jeden Original-Track die Segmente (nicht gemutete Marker-Frames).
      - Erzeugt für k Segmente insgesamt k Ziel-Tracks (Original + k-1 Duplikate).
      - Jeder Ziel-Track behält genau EIN Segment:
          * Alles VOR Segment-Start wird entfernt (UPTO).
          * Alles NACH Segment-Ende wird entfernt (REMAINED).
    Hinweise:
      - 'new_tracks' wird aus Kompatibilitätsgründen akzeptiert, aber intern nicht benötigt.
      - Duplikation erfolgt kontextlokal hier, damit dynamisch k-1 Kopien je Track entstehen.
    """
    tracks = space.clip.tracking.tracks

    # Arbeitskontext absichern
    with context.temp_override(area=area, region=region, space_data=space):
        for orig in list(original_tracks):
            # Segmente des Original-Tracks ermitteln
            try:
                segs = get_track_segments(orig)
            except Exception:
                segs = []

            # Weniger als 1 Segment → nichts zu tun
            if not segs:
                continue

            # Für k Segmente brauchen wir k Ziel-Tracks (Original + k-1 Kopien)
            k = len(segs)
            targets = [orig]

            # Zusätzliche Duplikate erzeugen (k-1 Stück)
            # Hinweis: Copy/Paste dupliziert NUR selektierte Tracks → wir isolieren die Selektion
            while len(targets) < k:
                dup = _duplicate_once(context, area, region, space, orig)
                if dup is None:
                    # Konnte nicht duplizieren → verbleibende Segmente können nicht separat gehalten werden
                    break
                targets.append(dup)

            # Jetzt weist jede targets[i] ein Segment segs[i] zu (sofern genug Duplikate vorhanden)
            # Für jedes Target: Nur das jeweilige Segment stehen lassen.
            # Vorgehen:
            #   1) Nach Segment-Ende löschen → action='REMAINED'
            #   2) Vor Segment-Beginn löschen → action='UPTO'
            # Reihenfolge ist wichtig, damit der gültige Bereich exakt [start, end] bleibt.
            limit = min(len(targets), len(segs))
            for idx in range(limit):
                t = targets[idx]
                seg_start, seg_end = segs[idx]

                # Nur diesen Track selektieren
                for tt in tracks:
                    tt.select = False
                t.select = True

                # 1) Alles nach Segment-Ende entfernen (REMAINED)
                try:
                    context.scene.frame_set(seg_end)
                    bpy.ops.clip.clear_track_path(action='REMAINED', clear_active=True)
                except Exception:
                    pass

                # 2) Alles vor Segment-Beginn entfernen (UPTO)
                try:
                    context.scene.frame_set(seg_start)
                    bpy.ops.clip.clear_track_path(action='UPTO', clear_active=True)
                except Exception:
                    pass

        # Schlanker UI-Refresh (kein Sleep, kein WIN_SWAP)
        try:
            bpy.ops.wm.redraw_timer(type='DRAW', iterations=1)
        except Exception:
            pass
        bpy.context.view_layer.update()
