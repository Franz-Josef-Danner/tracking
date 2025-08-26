import bpy
import time
from contextlib import contextmanager


@contextmanager
def clip_context(clip=None):
    """
    Kontext-Override für CLIP_EDITOR, damit clip.* Operatoren zuverlässig laufen.
    Wählt die erste CLIP_EDITOR-Area des aktiven Screens.
    """
    ctx = bpy.context.copy()
    area = next((a for a in bpy.context.window.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if area is None:
        raise RuntimeError("Kein 'Movie Clip Editor' (CLIP_EDITOR) im aktuellen Screen gefunden.")
    ctx['area'] = area
    ctx['region'] = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if clip is None:
        # Aktiven Clip der Area verwenden, falls vorhanden
        space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
        if space:
            clip = space.clip
    if clip:
        ctx['edit_movieclip'] = clip
    yield ctx


def _iter_tracks_with_marker_at_frame(tracks, frame):
    """
    Liefert Tracks, die im angegebenen Frame einen Marker haben (geschätzt oder exakt),
    und die nicht deaktiviert/gestummschaltet sind.
    """
    for tr in tracks:
        # Track-Enable prüfen (robuster als "mute", das es am Track nicht gibt)
        if hasattr(tr, "enabled") and not bool(getattr(tr, "enabled")):
            continue

        # Marker in diesem Frame finden (exact=False erlaubt interpolierten Zugriff)
        mk = tr.markers.find_frame(frame, exact=False)
        if mk is None:
            continue

        # Marker: 'mute' existiert ggf. → nur dann prüfen
        if hasattr(mk, "mute") and bool(getattr(mk, "mute")):
            continue

        yield tr


def refine_on_high_error(
    error_track: float,
    *,
    clip: bpy.types.MovieClip | None = None,
    tracking_object_name: str | None = None,
    only_selected_tracks: bool = False,
    wait_seconds: float = 0.1,
) -> None:
    """
    Durchläuft alle Frames der aktuellen Szene. Für jeden Frame:
      - MEA = Anzahl aktiver Marker (Tracks mit Marker in diesem Frame)
      - ME  = Summe der Track-Fehler (average_error) der aktiven Marker
      - FE  = ME / MEA (Durchschnitt je Marker)
      - Wenn FE > error_track * 2: Playhead auf Frame, refine_markers vorwärts & rückwärts.

    Hinweise
    --------
    Blender gibt per Python keinen pro-Frame-Fehler je Marker aus. Wir verwenden daher
    tr.average_error als ME_i-Näherung, sofern der Track im aktuellen Frame einen Marker besitzt.
    """
    scene = bpy.context.scene
    if scene is None:
        raise RuntimeError("Keine aktive Szene gefunden.")

    with clip_context(clip) as ctx:
        clip = ctx.get('edit_movieclip')
        if clip is None:
            raise RuntimeError("Kein Movie Clip verfügbar (weder über Parameter noch im Editor).")

        tracking = clip.tracking

        # Solve-Check
        recon = getattr(tracking, "reconstruction", None)
        if not recon or not getattr(recon, "is_valid", False):
            raise RuntimeError("Rekonstruktion ist nicht gültig. Bitte erst Solve durchführen.")

        # Tracking-Objekt bestimmen
        tob = (tracking.objects.get(tracking_object_name)
               if tracking_object_name else tracking.objects.active)
        if tob is None:
            raise RuntimeError("Kein Tracking-Objekt gefunden/aktiv.")

        tracks = list(tob.tracks)

        # Optional nur selektierte Tracks berücksichtigen
        if only_selected_tracks:
            tracks = [t for t in tracks if getattr(t, "select", False)]

        if not tracks:
            raise RuntimeError("Keine (passenden) Tracks gefunden.")

        frame_start = scene.frame_start
        frame_end = scene.frame_end

        triggered_frames = []

        for f in range(frame_start, frame_end + 1):
            # Aktive Marker/Tracks im Frame sammeln
            active_tracks = list(_iter_tracks_with_marker_at_frame(tracks, f))
            MEA = len(active_tracks)
            if MEA == 0:
                continue

            # ME als Summe aus average_error der betreffenden Tracks (defensiv)
            ME = 0.0
            for t in active_tracks:
                try:
                    ME += float(getattr(t, "average_error"))
                except Exception:
                    # falls ein Track kein average_error hat → ignorieren
                    pass
            FE = ME / MEA

            if FE > (error_track * 2.0):
                # Playhead setzen
                scene.frame_set(f)  # setzt auch DepGraph-Updates
                triggered_frames.append((f, FE, MEA))

                # Auswahl im MCE konsistent halten (nur falls only_selected_tracks=True)
                if only_selected_tracks:
                    # sicherstellen, dass Selektion stimmt (Operator arbeitet auf selektierten Markern)
                    for t in tob.tracks:
                        try:
                            t.select = False
                        except Exception:
                            pass
                    for t in active_tracks:
                        try:
                            t.select = True
                        except Exception:
                            pass

                # Refine vorwärts & rückwärts
                bpy.ops.clip.refine_markers(ctx, backwards=False)  # nach vorne
                # kurzer UI-Redraw + Wartezeit, um Feedback/Lag zu vermeiden
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                bpy.ops.clip.refine_markers(ctx, backwards=True)   # rückwärts
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        # Optional: kurzes Protokoll in der Konsole
        if triggered_frames:
            print("[RefineOnHighError] Ausgelöst bei Frames:")
            for f, fe, mea in triggered_frames:
                print(f"  Frame {f}: FE={fe:.4f} (MEA={mea}) > 2*error_track={2*error_track:.4f}")
        else:
            print("[RefineOnHighError] Keine Frames über Schwellwert gefunden.")


# Beispielaufruf:
# refine_on_high_error(
#     error_track=0.3,
#     clip=None,  # aktiven Clip aus dem Movie Clip Editor verwenden
#     tracking_object_name=None,  # aktives Tracking-Objekt
#     only_selected_tracks=False,
#     wait_seconds=0.1,
# )
