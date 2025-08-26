import bpy
import time
from contextlib import contextmanager
from math import isfinite


@contextmanager
def clip_context(clip=None):
    """
    Kontext-Override für CLIP_EDITOR, damit clip.* Operatoren zuverlässig laufen.
    Wählt die erste CLIP_EDITOR-Area des aktiven Screens.
    """
    ctx = bpy.context.copy()
    win = bpy.context.window
    scr = win.screen if win else None
    area = next((a for a in (scr.areas if scr else []) if a.type == 'CLIP_EDITOR'), None)
    if area is None:
        raise RuntimeError("Kein 'Movie Clip Editor' (CLIP_EDITOR) im aktuellen Screen gefunden.")
    ctx['window'] = win
    ctx['screen'] = scr
    ctx['area'] = area
    ctx['region'] = next((r for r in area.regions if r.type == 'WINDOW'), None)

    if clip is None:
        # Aktiven Clip der Area verwenden, falls vorhanden
        space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
        if space:
            clip = space.clip
    if clip:
        ctx['edit_movieclip'] = clip
        ctx['space_data'] = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)

    yield ctx


def _iter_tracks_with_marker_at_frame(tracks, frame):
    """
    Tracks mit Marker auf 'frame' (geschätzt/ exakt), die nicht deaktiviert sind.
    """
    for tr in tracks:
        if hasattr(tr, "enabled") and not bool(getattr(tr, "enabled")):
            continue
        mk = tr.markers.find_frame(frame, exact=False)
        if mk is None:
            continue
        if hasattr(mk, "mute") and bool(getattr(mk, "mute")):
            continue
        yield tr


def _marker_error_on_frame(track, frame):
    """
    Liefert möglichst den Marker-Error des Tracks auf 'frame';
    Fallback: track.average_error. Nicht-finite Werte -> None.
    """
    try:
        mk = track.markers.find_frame(frame, exact=False)
        if mk is not None and hasattr(mk, "error"):
            v = float(mk.error)
            if isfinite(v):
                return v
    except Exception:
        pass
    try:
        v = float(getattr(track, "average_error"))
        return v if isfinite(v) else None
    except Exception:
        return None


def _refine_markers_with_override(ctx: dict, *, backwards: bool) -> None:
    """
    Führt bpy.ops.clip.refine_markers sicher mit temp_override aus.
    """
    with bpy.context.temp_override(**ctx):
        bpy.ops.clip.refine_markers('EXEC_DEFAULT', backwards=bool(backwards))


def _set_selection_for_tracks(tob, frame, tracks_subset):
    """
    Setzt die Selektion ausschließlich auf 'tracks_subset' und deren Marker auf 'frame'.
    (per Property-Set, ohne Operator; robust gegen Kontext)
    """
    # Alles deselektieren
    for t in tob.tracks:
        try:
            t.select = False
            for m in t.markers:
                m.select = False
        except Exception:
            pass

    # Nur gewünschte Tracks + Marker auf diesem Frame selektieren
    for t in tracks_subset:
        try:
            mk = t.markers.find_frame(frame, exact=False)
            if mk is None:
                continue
            t.select = True
            mk.select = True
        except Exception:
            pass


def refine_on_high_error(
    error_track: float,
    *,
    clip: bpy.types.MovieClip | None = None,
    tracking_object_name: str | None = None,
    only_selected_tracks: bool = False,
    wait_seconds: float = 0.1,
    max_per_frame: int = 20,  # NEW: Obergrenze Top-N pro Frame
) -> None:
    """
    Durchläuft alle Frames der aktuellen Szene. Für jeden Frame:
      - MEA = Anzahl aktiver Marker (Tracks mit Marker in diesem Frame)
      - ME  = Summe der Track-Fehler (Marker.error- oder average_error-Fallback)
      - FE  = ME / MEA (Durchschnitt je Marker)
      - Wenn FE > error_track * 2:
          * Selektion = Top-N (max_per_frame) Tracks mit größtem Fehler in diesem Frame
          * refine_markers vorwärts & rückwärts

    Hinweise:
      - Auswahl wird immer auf die Top-N beschränkt.
      - Wenn only_selected_tracks=True, wird bereits die Eingangs-Trackliste
        auf zuvor selektierte Tracks gefiltert.
    """
    scene = bpy.context.scene
    if scene is None:
        raise RuntimeError("Keine aktive Szene gefunden.")

    with clip_context(clip) as ctx:
        clip = ctx.get('edit_movieclip')
        if clip is None:
            raise RuntimeError("Kein Movie Clip verfügbar (weder über Parameter noch im Editor).")

        tracking = clip.tracking
        recon = getattr(tracking, "reconstruction", None)
        if not recon or not getattr(recon, "is_valid", False):
            raise RuntimeError("Rekonstruktion ist nicht gültig. Bitte erst Solve durchführen.")

        # Tracking-Objekt bestimmen
        tob = (tracking.objects.get(tracking_object_name)
               if tracking_object_name else tracking.objects.active)
        if tob is None:
            raise RuntimeError("Kein Tracking-Objekt gefunden/aktiv.")

        tracks = list(tob.tracks)
        if only_selected_tracks:
            tracks = [t for t in tracks if getattr(t, "select", False)]
        if not tracks:
            raise RuntimeError("Keine (passenden) Tracks gefunden.")

        frame_start = scene.frame_start
        frame_end = scene.frame_end

        triggered_frames = []

        for f in range(frame_start, frame_end + 1):
            # Alle Tracks mit Marker auf f
            active_tracks = list(_iter_tracks_with_marker_at_frame(tracks, f))
            MEA = len(active_tracks)
            if MEA == 0:
                continue

            # FE (Frame-Mittel) für die Trigger-Entscheidung
            ME = 0.0
            for t in active_tracks:
                v = _marker_error_on_frame(t, f)
                if v is not None:
                    ME += v
            FE = ME / MEA

            if FE > (error_track * 2.0):
                # Top-N Tracks nach Fehler bestimmen (Marker.error bevorzugt)
                scored = []
                for t in active_tracks:
                    v = _marker_error_on_frame(t, f)
                    if v is not None:
                        scored.append((v, t))
                # sort desc und cap
                scored.sort(key=lambda kv: kv[0], reverse=True)
                top_tracks = [t for _, t in scored[:max(1, int(max_per_frame))]]
                if not top_tracks:
                    continue  # nichts Sinnvolles auszuwählen

                # Playhead setzen & Selection exakt auf Top-N beschränken
                scene.frame_set(f)
                _set_selection_for_tracks(tob, f, top_tracks)

                triggered_frames.append((f, FE, MEA, len(top_tracks)))

                # Refine vorwärts & rückwärts (nur Top-N selektiert)
                _refine_markers_with_override(ctx, backwards=False)
                with bpy.context.temp_override(**ctx):
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                _refine_markers_with_override(ctx, backwards=True)
                with bpy.context.temp_override(**ctx):
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        # Logging
        if triggered_frames:
            print("[RefineOnHighError] Ausgelöst bei Frames:")
            for f, fe, mea, nsel in triggered_frames:
                print(f"  Frame {f}: FE={fe:.4f} (MEA={mea}), Top-N selektiert: {nsel}")
        else:
            print("[RefineOnHighError] Keine Frames über Schwellwert gefunden.")


# Beispielaufruf:
# refine_on_high_error(
#     error_track=0.3,
#     clip=None,  # aktiven Clip aus dem Movie Clip Editor verwenden
#     tracking_object_name=None,  # aktives Tracking-Objekt
#     only_selected_tracks=False,
#     wait_seconds=0.1,
#     max_per_frame=20,
# )
