# refine_high_error.py
from __future__ import annotations
import bpy

__all__ = ("run_refine_on_high_error",)

# --- Context Utilities --------------------------------------------------------

def _find_clip_window(context):
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None, None, None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None

# --- UI Redraw Helper (neu) ---------------------------------------------------
def _pulse_ui(context, area=None, region=None):
    """Sofortiges Neuzeichnen der UI erzwingen (sichtbarer Framewechsel)."""
    try:
        if area:
            area.tag_redraw()
        with context.temp_override(window=context.window, area=area, region=region):
            bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
    except Exception:
        # Fallback: wenigstens Area zum Redraw markieren
        if area:
            area.tag_redraw()

# --- Clip-Editor Sync Helper --------------------------------------------------
def _sync_clip_editor_frame(space_ce, frame: int):
    """Sorgt dafür, dass der CLIP_EDITOR wirklich den gewünschten Frame zeigt."""
    # In Blender gibt es je nach Version zwei Wege:
    # 1) Editor auf Szenen-Frame syncen (wenn vorhanden)
    if hasattr(space_ce, "use_scene_frame"):
        space_ce.use_scene_frame = True

    # 2) Safety: explizit die Editor-Ansicht und den Clip-User-Frame setzen
    #    (falls der Editor seine eigene Zeit führt)
    if hasattr(space_ce, "view"):
        # sicherstellen, dass wir in der CLIP-Ansicht sind (nicht GRAPH/DOPESHEET)
        try:
            space_ce.view = 'CLIP'
        except Exception:
            pass

    # einige Builds führen eine eigene Zeit im Clip-User:
    cu = getattr(space_ce, "clip_user", None)
    if cu and hasattr(cu, "frame_current"):
        cu.frame_current = int(frame)

    # falls der Zeitcursor „gelockt“ ist, folgt die Ansicht nicht
    if hasattr(space_ce, "lock_time_cursor"):
        space_ce.lock_time_cursor = False

def _get_active_clip(context):
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _prev_next_keyframes(track, frame):
    prev_k, next_k = None, None
    for m in track.markers:
        if not m.is_keyed:
            continue
        if m.frame < frame and (prev_k is None or m.frame > prev_k):
            prev_k = m.frame
        if m.frame > frame and (next_k is None or m.frame < next_k):
            next_k = m.frame
    return prev_k, next_k


# --- Error-Serie --------------------------------------------------------------

def _build_error_series(recon):
    """frame -> average_error (float) aus Reconstruction Cameras."""
    series = {}
    for cam in getattr(recon, "cameras", []):
        try:
            series[int(cam.frame)] = float(cam.average_error)
        except Exception:
            continue
    return dict(sorted(series.items()))


# --- Neue Selektion: Alle Frames über High-Threshold --------------------------

def _select_frames_over_high_threshold(context, recon):
    """
    Wählt *alle* Frames f im Szenenbereich, deren Error > (scene.error_track * 10) ist.
    Gibt sortierte Frame-Indices zurück.
    """
    scene = context.scene
    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)

    # Schwelle aus UI-Property (Default 2.0), High-Threshold = *10
    base = float(getattr(scene, "error_track", 2.0) or 2.0)  # siehe UI-Property in __init__.py
    high_threshold = base * 10.0

    series = _build_error_series(recon)
    # Szenenbereich filtern
    series = {f: e for f, e in series.items() if frame_start <= f <= frame_end}

    # Auswahl nach High-Threshold
    selected = sorted(f for f, e in series.items() if e > high_threshold)

    print(f"[Select] Bereich {frame_start}–{frame_end}, error_track={base:.3f} "
          f"→ high_threshold={high_threshold:.3f}")
    if selected:
        # zur Transparenz Fehlerwerte anzeigen (Top zuerst)
        preview = sorted(((f, series[f]) for f in selected), key=lambda kv: (-kv[1], kv[0]))
        print("[Select] Frames über Schwelle:", [f for f, _ in preview])
        print("[Select] Fehler (desc):", [round(err, 3) for _, err in preview[:10]])
    else:
        print("[Select] Keine Frames über high_threshold gefunden.")
    return selected

class _RefinePump:
    def __init__(self, context, clip, bad_frames, area, region, space_ce, resolve_after, original_frame):
        self.context = context
        self.clip = clip
        self.bad_frames = list(bad_frames)
        self.area, self.region, self.space_ce = area, region, space_ce
        self.resolve_after = resolve_after
        self.original_frame = original_frame
        self.processed = 0
        self.scene = context.scene
        self._cancelled = False

    def _pulse(self):
        try:
            if self.area:
                self.area.tag_redraw()
            with self.context.temp_override(window=self.context.window, area=self.area, region=self.region):
                bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
        except Exception:
            if self.area:
                self.area.tag_redraw()

    def _do_refine_one(self, f):
        scene = self.scene
        clip = self.clip
        print(f"\n[FRAME] Refine für Frame {f}")
        scene.frame_set(f)
        # falls du _sync_clip_editor_frame hast, hier optional:
        # _sync_clip_editor_frame(self.space_ce, f)
        self._pulse()

        tracks_forward, tracks_backward = [], []
        for tr in clip.tracking.tracks:
            if getattr(tr, "hide", False) or getattr(tr, "lock", False):
                continue
            prev_k, next_k = _prev_next_keyframes(tr, f)
            mk = tr.markers.find_frame(f, exact=True)
            if mk and getattr(mk, "mute", False):
                continue
            if prev_k is not None:
                tracks_forward.append(tr)
            if next_k is not None:
                tracks_backward.append(tr)

        print(f"  → Vorwärts: {len(tracks_forward)} | Rückwärts: {len(tracks_backward)}")

        if tracks_forward:
            with self.context.temp_override(area=self.area, region=self.region, space_data=self.space_ce):
                for tr in clip.tracking.tracks:
                    tr.select = False
                for tr in tracks_forward:
                    tr.select = True
                bpy.ops.clip.refine_markers(backwards=False)
        if tracks_backward:
            with self.context.temp_override(area=self.area, region=self.region, space_data=self.space_ce):
                for tr in clip.tracking.tracks:
                    tr.select = False
                for tr in tracks_backward:
                    tr.select = True
                bpy.ops.clip.refine_markers(backwards=True)

        self.processed += 1
        print(f"  [DONE] Frame {f} abgeschlossen.")
        self._pulse()

    def tick(self):
        # Abbruch/Ende?
        if self._cancelled:
            return None

        if not self.bad_frames:
            if self.resolve_after:
                print("[ACTION] Starte erneutes Kamera-Solve…")
                with self.context.temp_override(area=self.area, region=self.region, space_data=self.space_ce):
                    bpy.ops.clip.solve_camera()
                # _sync_clip_editor_frame(self.space_ce, self.scene.frame_current)
                self._pulse()
                print("[DONE] Kamera-Solve abgeschlossen.")

            # zurück auf ursprünglichen Frame
            self.scene.frame_set(self.original_frame)
            # _sync_clip_editor_frame(self.space_ce, self.original_frame)
            self._pulse()
            print(f"\n[SUMMARY] Insgesamt bearbeitet: {self.processed} Frame(s)")
            return None  # Timer endet

        # Nächstes Stück Arbeit:
        f = self.bad_frames.pop(0)
        self._do_refine_one(f)

        # sofort wieder schedulen (0.0) → UI bekommt Event‑Loop
        return 0.0

# --- Core Routine -------------------------------------------------------------

def run_refine_on_high_error(
    context,
    limit_frames: int = 0,
    resolve_after: bool = False,
    # --- Backward-Compat (ignoriert, aber akzeptiert) ---
    error_threshold: float | None = None,
    **_compat_ignored,
) -> int:
    """
    Refine auf allen Frames mit Solve-Frame-Error > (scene.error_track * 10).

    Optional: limit_frames > 0 begrenzt die Anzahl der zu bearbeitenden Frames.
    Hinweis: 'error_threshold' und weitere Alt-Argumente sind nur für Kompatibilität vorhanden.
    """
    if error_threshold is not None:
        print("[Refine][Compat] 'error_threshold' übergeben, wird im High-Threshold-Modus ignoriert.")
    if _compat_ignored:
        print(f"[Refine][Compat] Ignoriere zusätzliche Alt-Argumente: {list(_compat_ignored.keys())}")

    clip = _get_active_clip(context)
    if not clip:
        raise RuntimeError("Kein MovieClip geladen.")

    obj = clip.tracking.objects.active
    recon = obj.reconstruction
    if not getattr(recon, "is_valid", False):
        raise RuntimeError("Keine gültige Rekonstruktion gefunden (Solve fehlt oder wurde gelöscht).")

    # --- Frame-Selektion (neu) ---
    bad_frames = _select_frames_over_high_threshold(context, recon)

    # Optional zusätzlich begrenzen
    if limit_frames > 0 and bad_frames:
        bad_frames = bad_frames[:int(limit_frames)]

    if not bad_frames:
        print("[INFO] Keine Frames über High-Threshold gefunden.")
        return 0

    area, region, space_ce = _find_clip_window(context)
    if not area:
        raise RuntimeError("Kein CLIP_EDITOR-Fenster gefunden (Kontext erforderlich).")

    scene = context.scene
    original_frame = scene.frame_current
    # --- NEU: Timer-Pump statt for-Schleife ---
    pump = _RefinePump(context, clip, bad_frames, area, region, space_ce, resolve_after, original_frame)
    bpy.app.timers.register(pump.tick, first_interval=0.0)
    print(f"[INFO] Refine (High-Error) gestartet: {len(bad_frames)} Frames, UI bleibt responsiv.")
    return 0  # Rückgabe sofort; Arbeit läuft im Timer
    processed = 0

    for f in bad_frames:
        print(f"\n[FRAME] Refine für Frame {f}")
        scene.frame_set(f)
        
        _sync_clip_editor_frame(space_ce, f)
        _pulse_ui(context, area=area, region=region)
        
        tracks_forward, tracks_backward = [], []
        for tr in clip.tracking.tracks:
            if getattr(tr, "hide", False) or getattr(tr, "lock", False):
                continue
            prev_k, next_k = _prev_next_keyframes(tr, f)
            mk = tr.markers.find_frame(f, exact=True)
            if mk and getattr(mk, "mute", False):
                continue
            if prev_k is not None:
                tracks_forward.append(tr)
            if next_k is not None:
                tracks_backward.append(tr)

        print(f"  → Vorwärts: {len(tracks_forward)} | Rückwärts: {len(tracks_backward)}")

        if tracks_forward:
            with context.temp_override(area=area, region=region, space_data=space_ce):
                for tr in clip.tracking.tracks:
                    tr.select = False
                for tr in tracks_forward:
                    tr.select = True
                bpy.ops.clip.refine_markers(backwards=False)

        if tracks_backward:
            with context.temp_override(area=area, region=region, space_data=space_ce):
                for tr in clip.tracking.tracks:
                    tr.select = False
                for tr in tracks_backward:
                    tr.select = True
                bpy.ops.clip.refine_markers(backwards=True)

        processed += 1
        print(f"  [DONE] Frame {f} abgeschlossen.")

    if resolve_after:
        print("[ACTION] Starte erneutes Kamera-Solve…")
        with context.temp_override(area=area, region=region, space_data=space_ce):
            bpy.ops.clip.solve_camera()
        _sync_clip_editor_frame(space_ce, scene.frame_current)
        _pulse_ui(context, area=area, region=region)
        print("[DONE] Kamera-Solve abgeschlossen.")

    scene.frame_set(original_frame)
    _sync_clip_editor_frame(space_ce, original_frame)
    _pulse_ui(context, area=area, region=region)  # UI auf ursprünglichem Frame aktualisieren
    print(f"\n[SUMMARY] Insgesamt bearbeitet: {processed} Frame(s)")
    return processed
