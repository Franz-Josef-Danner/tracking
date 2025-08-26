import bpy
import time
from contextlib import contextmanager
from math import isfinite


@contextmanager
def clip_context(clip=None):
    """
    Kontext-Override für CLIP_EDITOR (window/screen/area/region/space_data/edit_movieclip).
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
    space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)

    if clip is None and space:
        clip = space.clip
    if clip:
        ctx['edit_movieclip'] = clip
    if space:
        ctx['space_data'] = space
    yield ctx


# ---------- UI-Helpers -------------------------------------------------------

def _scene_to_clip_frame(context, clip, scene_frame: int) -> int:
    """Szenen-Frame deterministisch auf Clip-Frame mappen (fps/Offsets/Clamping)."""
    scn = context.scene
    scene_start = int(getattr(scn, "frame_start", 1))
    clip_start = int(getattr(clip, "frame_start", 1))
    scn_fps = float(getattr(getattr(scn, "render", None), "fps", 0) or 0.0)
    clip_fps = float(getattr(clip, "fps", 0) or 0.0)
    scale = (clip_fps / scn_fps) if (scn_fps > 0.0 and clip_fps > 0.0) else 1.0
    rel = round((scene_frame - scene_start) * scale)
    f = int(clip_start + rel)
    dur = int(getattr(clip, "frame_duration", 0) or 0)
    if dur > 0:
        fmin, fmax = clip_start, clip_start + dur - 1
        f = max(fmin, min(f, fmax))
    return f


def _force_visible_playhead(ctx: dict, scene: bpy.types.Scene, clip: bpy.types.MovieClip,
                            scene_frame: int, *, sleep_s: float = 0.06) -> None:
    """
    Setzt Playhead sichtbar auf scene_frame:
      - Szene-Frame setzen
      - Clip-User-Frame synchronisieren (bei fps/Offset-Differenzen)
      - View-Layer updaten
      - 2× Redraw anstoßen
      - kurze Wartezeit für zuverlässiges Zeichnen
    """
    # 1) Szene-Frame setzen
    scene.frame_set(int(scene_frame))

    # 2) Clip-Frame im Editor mitziehen
    try:
        clip_frame = _scene_to_clip_frame(bpy.context, clip, int(scene_frame))
        space = ctx.get("space_data", None)
        if space and getattr(space, "clip_user", None):
            space.clip_user.frame_current = int(clip_frame)
    except Exception:
        pass

    # 3) Layer/Depsgraph aktualisieren (stellt sicher, dass UI gültige Daten hat)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    # 4) Harte Redraw-Sequenz
    try:
        area = ctx.get("area", None)
        if area:
            area.tag_redraw()
        with bpy.context.temp_override(**ctx):
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        if area:
            area.tag_redraw()
        with bpy.context.temp_override(**ctx):
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

    # 5) winzige Pause lässt den Playhead wirklich erscheinen
    if sleep_s and sleep_s > 0.0:
        try:
            time.sleep(float(sleep_s))
        except Exception:
            pass


# ---------- Fehler-/Selektion-Helpers ---------------------------------------

def _iter_tracks_with_marker_at_frame(tracks, frame):
    """Tracks mit Marker auf 'frame' (geschätzt/ exakt), die nicht deaktiviert sind."""
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
    """Bevorzugt Marker.error auf 'frame', sonst track.average_error. Non-finite → None."""
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
    """Sicherer refine_markers-Aufruf mit gültigem Kontext."""
    with bpy.context.temp_override(**ctx):
        bpy.ops.clip.refine_markers('EXEC_DEFAULT', backwards=bool(backwards))


def _set_selection_for_tracks(tob, frame, tracks_subset):
    """Selektion ausschließlich auf 'tracks_subset' und deren Marker auf 'frame' setzen."""
    for t in tob.tracks:
        try:
            t.select = False
            for m in t.markers:
                m.select = False
        except Exception:
            pass
    for t in tracks_subset:
        try:
            mk = t.markers.find_frame(frame, exact=False)
            if mk is None:
                continue
            t.select = True
            mk.select = True
        except Exception:
            pass


# ---------- Hauptfunktion ----------------------------------------------------

def refine_on_high_error(
    error_track: float,
    *,
    clip: bpy.types.MovieClip | None = None,
    tracking_object_name: str | None = None,
    only_selected_tracks: bool = False,
    wait_seconds: float = 0.05,
    max_per_frame: int = 20,          # Top-N Marker pro Frame
    ui_preview: bool = True,          # Playhead sichtbar springen lassen
    ui_sleep_s: float = 0.06,         # kleine Wartezeit für Rendering des Cursors
) -> None:
    """
    Durchläuft alle Frames; wenn FE > error_track*2:
      - Selektion = Top-N (max_per_frame) Tracks mit größtem Fehler in diesem Frame
      - zeigt Playhead-Sprung (wenn ui_preview=True)
      - refine_markers vorwärts & rückwärts.
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
            act = list(_iter_tracks_with_marker_at_frame(tracks, f))
            MEA = len(act)
            if MEA == 0:
                continue

            ME = 0.0
            scored = []
            for t in act:
                v = _marker_error_on_frame(t, f)
                if v is None:
                    continue
                ME += v
                scored.append((v, t))
            if not scored:
                continue
            FE = ME / max(1, MEA)

            if FE > (error_track * 2.0):
                # Top-N bestimmen
                scored.sort(key=lambda kv: kv[0], reverse=True)
                top_tracks = [t for _, t in scored[:max(1, int(max_per_frame))]]

                # Playhead sichtbar setzen
                if ui_preview:
                    _force_visible_playhead(ctx, scene, clip, f, sleep_s=ui_sleep_s)
                else:
                    scene.frame_set(f)

                _set_selection_for_tracks(tob, f, top_tracks)
                triggered_frames.append((f, FE, MEA, len(top_tracks)))

                # Refine vorwärts & rückwärts
                _refine_markers_with_override(ctx, backwards=False)
                with bpy.context.temp_override(**ctx):
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                _refine_markers_with_override(ctx, backwards=True)
                with bpy.context.temp_override(**ctx):
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        if triggered_frames:
            print("[RefineOnHighError] Ausgelöst bei Frames:")
            for f, fe, mea, nsel in triggered_frames:
                print(f"  Frame {f}: FE={fe:.4f} (MEA={mea}), Top-N selektiert: {nsel}")
        else:
            print("[RefineOnHighError] Keine Frames über Schwellwert gefunden.")
