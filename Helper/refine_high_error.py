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


# ---------- Frame-Mapping & UI -----------------------------------------------

def _scene_to_clip_frame(context, clip, scene_frame: int) -> int:
    """Szenen-Frame → Clip-Frame (beachtet fps/Offsets; geklemmt auf Clipdauer)."""
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
                            scene_frame: int, clip_frame: int, *, sleep_s: float = 0.06) -> None:
    """
    Playhead sichtbar setzen:
      - Szene-Frame setzen
      - Clip-User-Frame synchronisieren
      - View-Layer updaten
      - zwei Redraw-Zyklen
      - kurze Pause für zuverlässiges Zeichnen
    """
    scene.frame_set(int(scene_frame))

    try:
        space = ctx.get("space_data", None)
        if space and getattr(space, "clip_user", None):
            space.clip_user.frame_current = int(clip_frame)
    except Exception:
        pass

    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

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

    if sleep_s and sleep_s > 0.0:
        try:
            time.sleep(float(sleep_s))
        except Exception:
            pass


# ---------- Marker/Track-Helpers --------------------------------------------

def _find_marker_on_clip_frame(track, frame_clip: int):
    try:
        return track.markers.find_frame(frame_clip, exact=False)
    except Exception:
        return None


def _iter_tracks_with_marker_at_clip_frame(tracks, frame_clip: int):
    """Tracks mit Marker auf 'frame_clip', die nicht deaktiviert und nicht gemutet sind."""
    for tr in tracks:
        if hasattr(tr, "enabled") and not bool(getattr(tr, "enabled")):
            continue
        mk = _find_marker_on_clip_frame(tr, frame_clip)
        if mk is None:
            continue
        if hasattr(mk, "mute") and bool(getattr(mk, "mute")):
            continue
        yield tr


def _marker_error_on_clip_frame(track, frame_clip: int):
    """Bevorzugt Marker.error auf 'frame_clip', sonst track.average_error. Non-finite → None."""
    try:
        mk = _find_marker_on_clip_frame(track, frame_clip)
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


def _set_selection_for_tracks_on_clip_frame(tob, frame_clip: int, tracks_subset):
    """Selektion ausschließlich auf 'tracks_subset' und deren Marker auf 'frame_clip' setzen."""
    for t in tob.tracks:
        try:
            t.select = False
            for m in t.markers:
                m.select = False
        except Exception:
            pass
    for t in tracks_subset:
        try:
            mk = _find_marker_on_clip_frame(t, frame_clip)
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
    ui_preview: bool = True,          # Playhead sichtbar springen lassen
    ui_sleep_s: float = 0.06,         # kleine Wartezeit für Rendering des Cursors
    max_refine_calls: int = 20,       # NEU: Maximale Anzahl Operator-Aufrufe insgesamt
) -> None:
    """
    Durchläuft alle Frames; wenn FE > error_track*2:
      - selektiert ALLE Tracks mit Marker im Frame
      - zeigt Playhead-Sprung (wenn ui_preview=True)
      - ruft refine_markers vorwärts und (falls Budget) rückwärts auf
    Gesamtlimit: max_refine_calls zählt **jede** Operator-Ausführung (vorwärts oder rückwärts).
    """
    scene = bpy.context.scene
    if scene is None:
        raise RuntimeError("Keine aktive Szene gefunden.")

    if int(max_refine_calls) <= 0:
        print("[RefineOnHighError] max_refine_calls == 0 → nichts zu tun.")
        return

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

        refine_ops = 0
        triggered_frames = []

        for f_scene in range(frame_start, frame_end + 1):
            if refine_ops >= int(max_refine_calls):
                break

            f_clip = _scene_to_clip_frame(bpy.context, clip, f_scene)

            act = list(_iter_tracks_with_marker_at_clip_frame(tracks, f_clip))
            MEA = len(act)
            if MEA == 0:
                continue

            # FE = Frame-Mittel der Fehler (Marker.error bevorzugt)
            ME = 0.0
            for t in act:
                v = _marker_error_on_clip_frame(t, f_clip)
                if v is not None:
                    ME += v
            FE = ME / max(1, MEA)

            if FE > (error_track * 2.0):
                # Sichtbarer Sprung des Playheads
                if ui_preview:
                    _force_visible_playhead(ctx, scene, clip, f_scene, f_clip, sleep_s=ui_sleep_s)
                else:
                    scene.frame_set(f_scene)

                # Selektion = alle aktiven Marker dieses Frames
                _set_selection_for_tracks_on_clip_frame(tob, f_clip, act)
                triggered_frames.append((f_scene, FE, MEA))

                # refine vorwärts
                if refine_ops < int(max_refine_calls):
                    _refine_markers_with_override(ctx, backwards=False)
                    refine_ops += 1
                    with bpy.context.temp_override(**ctx):
                        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

                # refine rückwärts (nur, wenn Budget vorhanden)
                if refine_ops < int(max_refine_calls):
                    if wait_seconds > 0:
                        time.sleep(wait_seconds)
                    _refine_markers_with_override(ctx, backwards=True)
                    refine_ops += 1
                    with bpy.context.temp_override(**ctx):
                        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        # Logging
        if triggered_frames:
            print(f"[RefineOnHighError] Frames ausgelöst: {len(triggered_frames)} | "
                  f"Operator-Aufrufe gesamt: {refine_ops}/{int(max_refine_calls)}")
            for f, fe, mea in triggered_frames[:10]:
                print(f"  Frame {f}: FE={fe:.4f} (MEA={mea})")
            if len(triggered_frames) > 10:
                print(f"  … (+{len(triggered_frames)-10} weitere Frames)")
        else:
            print("[RefineOnHighError] Keine Frames über Schwellwert gefunden.")
