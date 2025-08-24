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


# --- UI Redraw Helper ---------------------------------------------------------
def _pulse_ui(context, area=None, region=None):
    """Sofortiges Neuzeichnen der UI erzwingen."""
    try:
        if area:
            area.tag_redraw()
        with context.temp_override(window=context.window, area=area, region=region):
            bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
    except Exception:
        if area:
            area.tag_redraw()


# --- Core Helpers -------------------------------------------------------------

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


def _build_error_series(recon):
    series = {}
    for cam in getattr(recon, "cameras", []):
        try:
            series[int(cam.frame)] = float(cam.average_error)
        except Exception:
            continue
    return dict(sorted(series.items()))


def _select_frames_over_high_threshold(context, recon):
    scene = context.scene
    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)

    base = float(getattr(scene, "error_track", 2.0) or 2.0)
    high_threshold = base * 10.0

    series = _build_error_series(recon)
    series = {f: e for f, e in series.items() if frame_start <= f <= frame_end}
    selected = sorted(f for f, e in series.items() if e > high_threshold)

    print(f"[Select] Bereich {frame_start}–{frame_end}, "
          f"error_track={base:.3f} → high_threshold={high_threshold:.3f}")
    if selected:
        preview = sorted(((f, series[f]) for f in selected), key=lambda kv: (-kv[1], kv[0]))
        print("[Select] Frames über Schwelle:", [f for f, _ in preview])
        print("[Select] Fehler (desc):", [round(err, 3) for _, err in preview[:10]])
    else:
        print("[Select] Keine Frames über high_threshold gefunden.")
    return selected


# --- Pump (non-blocking Refine) -----------------------------------------------

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

    def _refine_one(self, f: int):
        scene = self.scene
        clip = self.clip
        scene.frame_set(f)

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

    def tick(self):
        if not self.bad_frames:
            if self.resolve_after:
                with self.context.temp_override(area=self.area, region=self.region, space_data=self.space_ce):
                    bpy.ops.clip.solve_camera()
            # restore
            self.scene.frame_set(self.original_frame)
            _pulse_ui(self.context, self.area, self.region)
            print(f"[SUMMARY] Insgesamt bearbeitet: {self.processed} Frame(s)")
            return None  # stop timer

        f = self.bad_frames.pop(0)
        self._refine_one(f)
        return 0.0  # sofort wieder schedulen


# --- Public API ---------------------------------------------------------------

def run_refine_on_high_error(
    context,
    limit_frames: int = 0,
    resolve_after: bool = False,
    error_threshold: float | None = None,
    **_compat_ignored,
) -> int:
    if error_threshold is not None:
        print("[Refine][Compat] 'error_threshold' wird ignoriert.")
    if _compat_ignored:
        print(f"[Refine][Compat] Ignoriere Alt-Args: {list(_compat_ignored.keys())}")

    clip = _get_active_clip(context)
    if not clip:
        raise RuntimeError("Kein MovieClip geladen.")

    obj = clip.tracking.objects.active
    recon = obj.reconstruction
    if not getattr(recon, "is_valid", False):
        raise RuntimeError("Keine gültige Rekonstruktion gefunden.")

    bad_frames = _select_frames_over_high_threshold(context, recon)
    if limit_frames > 0 and bad_frames:
        bad_frames = bad_frames[:int(limit_frames)]

    if not bad_frames:
        print("[INFO] Keine Frames über High-Threshold gefunden.")
        return 0

    area, region, space_ce = _find_clip_window(context)
    if not area:
        raise RuntimeError("Kein CLIP_EDITOR-Fenster gefunden.")

    pump = _RefinePump(context, clip, bad_frames, area, region, space_ce,
                       resolve_after, context.scene.frame_current)
    bpy.app.timers.register(pump.tick, first_interval=0.0)
    print(f"[INFO] Refine gestartet: {len(bad_frames)} Frames (asynchron).")
    return 0
