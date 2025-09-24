from .metrics_provider import TrackingMetrics, MetricsProvider
import time
from typing import Optional


class BlenderMetricsProvider(MetricsProvider):
    """Best-effort MetricsProvider that reads available tracking information from Blender's
    Movie Clip Editor via `bpy`. The implementation is defensive: it will fall back to
    synthetic defaults when running outside Blender or if attributes are missing.

    Assumptions:
    - `roi_id` is either an integer index into `clip.tracking.tracks` or the track name.
    - For per-frame values we try to find a marker at `frame` or the nearest marker.
    - Some attributes used here (e.g. `marker.correlation`, `marker.error`,
      `marker.pattern_corners`) may not be present in all Blender versions; access is
      wrapped in try/except and falls back to sensible defaults.
    """

    def __init__(self, *, clip: Optional[object] = None):
        self.clip = clip

    def _find_clip(self):
        try:
            import bpy  # type: ignore

            clip = getattr(bpy.context, "edit_movieclip", None) or getattr(
                getattr(bpy.context, "space_data", None), "clip", None
            )
            if clip is None:
                # fallback: take first movieclip in the blend file
                try:
                    clip = bpy.data.movieclips[0] if len(bpy.data.movieclips) > 0 else None
                except Exception:
                    clip = None
            return bpy, clip
        except Exception:
            return None, None

    def fetch_tracking_metrics(self, roi_id: str, frame: int) -> TrackingMetrics:
        t0 = time.time()
        bpy, clip = self._find_clip()

        # Synthetic fallback values (kept compatible with TrackingMetrics shape)
        fallback = {
            "corr": 0.0,
            "residual_px": 0.0,
            "lost": True,
            "jump_px": 0.0,
            "scale_delta": 0.0,
            "rot_delta": 0.0,
            "time_ms": 0.0,
        }

        if bpy is None or clip is None:
            # Not running inside Blender / no clip available
            dt_ms = (time.time() - t0) * 1000.0
            fallback["time_ms"] = float(dt_ms)
            out = {}
            for k, v in fallback.items():
                if isinstance(v, bool):
                    out[k] = v
                elif isinstance(v, (int, float)):
                    out[k] = float(v)
                else:
                    out[k] = v
            return out

        tracks = getattr(getattr(clip, "tracking", None), "tracks", None)
        if not tracks:
            dt_ms = (time.time() - t0) * 1000.0
            fallback["time_ms"] = float(dt_ms)
            return {k: float(v) if isinstance(v, (int, float)) else v for k, v in fallback.items()}

        # Resolve roi_id -> track (index or name)
        track = None
        try:
            idx = int(roi_id)
            if 0 <= idx < len(tracks):
                track = tracks[idx]
        except Exception:
            pass

        if track is None:
            # Try to find a track with a custom roi_id property (if orchestrator annotated it)
            for t in tracks:
                try:
                    v = getattr(t, "roi_id", None)
                    if v is None:
                        try:
                            # some bpy types allow dict-like access
                            v = t.get("roi_id", None)
                        except Exception:
                            v = v
                    if v is not None and str(int(v)) == str(roi_id):
                        track = t
                        break
                except Exception:
                    continue

        if track is None:
            # fallback: name exact match
            for t in tracks:
                try:
                    if t.name == roi_id:
                        track = t
                        break
                except Exception:
                    continue

        if track is None:
            # fallback: name patterns like 'roi_{id}' or containing the id
            needle1 = f"roi_{roi_id}"
            needle2 = f"roi{roi_id}"
            for t in tracks:
                try:
                    n = getattr(t, "name", "") or ""
                    if needle1 in n or needle2 in n or n.endswith(f"_{roi_id}"):
                        track = t
                        break
                except Exception:
                    continue

        if track is None:
            # fallback: any selected track
            for t in tracks:
                try:
                    if bool(getattr(t, "select", False)):
                        track = t
                        break
                except Exception:
                    continue

        if track is None:
            dt_ms = (time.time() - t0) * 1000.0
            fallback["time_ms"] = float(dt_ms)
            out = {}
            for k, v in fallback.items():
                if isinstance(v, bool):
                    out[k] = v
                elif isinstance(v, (int, float)):
                    out[k] = float(v)
                else:
                    out[k] = v
            return out

        # Try to extract per-frame marker and metrics (best-effort)
        corr = 0.0
        residual_px = 0.0
        lost = False
        jump_px = 0.0
        scale_delta = 0.0
        rot_delta = 0.0

        try:
            # Tracks may expose their marker list as `markers` or `markers.items()` depending on API
            markers = []
            if hasattr(track, "markers"):
                try:
                    markers = list(getattr(track, "markers") or [])
                except Exception:
                    markers = []
            else:
                # older/alternative api names
                try:
                    markers = list(getattr(track, "tracked_points") or [])
                except Exception:
                    markers = []
            # find marker at exact frame or nearest one
            marker = None
            for m in markers:
                try:
                    if int(getattr(m, "frame", -999999)) == int(frame):
                        marker = m
                        break
                except Exception:
                    continue
            if marker is None and markers:
                marker = min(markers, key=lambda m: abs(int(getattr(m, "frame", 0)) - int(frame)))

            # correlation: many Blender versions expose `marker.correlation` or `marker.corr`;
            # fall back to 0.0 if not present
            if marker is not None:
                corr = float(getattr(marker, "correlation", getattr(marker, "corr", 0.0) or 0.0))
                # check for marker flags that indicate lost/hidden
                lost = bool(getattr(marker, "hide", False) or getattr(marker, "mute", False) or getattr(marker, "disabled", False))

            # residual / solve error: try various possible attribute names
            residual_px = 0.0
            try:
                residual_px = float(getattr(track, "error", getattr(track, "average_error", None) or 0.0) or 0.0)
            except Exception:
                residual_px = float(getattr(marker, "error", 0.0) or 0.0)

            # jump_px: estimate displacement from previous marker (in pixels if clip size known)
            prev = None
            if markers:
                try:
                    prevs = [m for m in markers if int(getattr(m, "frame", 0)) < int(frame)]
                    if prevs:
                        prev = prevs[-1]
                except Exception:
                    prev = None

            if prev is not None and marker is not None:
                co1 = getattr(prev, "co", None) or getattr(prev, "pos", None) or getattr(prev, "co", None)
                co2 = getattr(marker, "co", None) or getattr(marker, "pos", None) or getattr(marker, "co", None)
                if co1 is not None and co2 is not None:
                    try:
                        # co are usually normalized coordinates (0..1). Try to scale with clip size if available
                        # MovieClip stores size as `size` or `resolution` in different versions
                        w = getattr(clip, "size", None) or getattr(clip, "resolution", None)
                        if w and isinstance(w, (tuple, list)) and len(w) >= 2:
                            sx = w[0]
                            sy = w[1]
                        else:
                            # Fallback: assume normalized canvas of 1.0 -> translate to pixels later if needed
                            sx = sy = 1.0
                        dx = (co1[0] - co2[0]) * sx
                        dy = (co1[1] - co2[1]) * sy
                        jump_px = (dx * dx + dy * dy) ** 0.5
                    except Exception:
                        jump_px = 0.0

            # scale_delta / rot_delta: best-effort via pattern_corners area & angle
            def _area(corners):
                try:
                    pts = list(corners)
                    if len(pts) >= 4:
                        a = 0.0
                        for i in range(4):
                            x1, y1 = float(pts[i][0]), float(pts[i][1])
                            x2, y2 = float(pts[(i + 1) % 4][0]), float(pts[(i + 1) % 4][1])
                            a += x1 * y2 - x2 * y1
                        return abs(a) / 2.0
                except Exception:
                    return 0.0
                return 0.0

            def _angle(corners):
                try:
                    import math

                    pts = list(corners)
                    cx = sum(p[0] for p in pts) / len(pts)
                    cy = sum(p[1] for p in pts) / len(pts)
                    dx = pts[0][0] - cx
                    dy = pts[0][1] - cy
                    return math.atan2(dy, dx)
                except Exception:
                    return 0.0

            if prev is not None and marker is not None:
                pc_prev = getattr(prev, "pattern_corners", None)
                pc_cur = getattr(marker, "pattern_corners", None)
                a1 = _area(pc_prev) if pc_prev is not None else 0.0
                a2 = _area(pc_cur) if pc_cur is not None else 0.0
                if a1:
                    scale_delta = (a2 - a1) / a1
                if pc_prev and pc_cur:
                    rot_delta = float(_angle(pc_cur) - _angle(pc_prev))

        except Exception:
            # Defensive: if anything in the Blender extraction fails, fall back to safe defaults
            corr = corr or 0.0
            residual_px = residual_px or 0.0
            lost = bool(lost)
            jump_px = jump_px or 0.0
            scale_delta = scale_delta or 0.0
            rot_delta = rot_delta or 0.0

        dt_ms = (time.time() - t0) * 1000.0
        return {
            "corr": float(max(0.0, min(1.0, corr or 0.0))),
            "residual_px": float(residual_px or 0.0),
            "lost": bool(lost),
            "jump_px": float(jump_px or 0.0),
            "scale_delta": float(scale_delta or 0.0),
            "rot_delta": float(rot_delta or 0.0),
            "time_ms": float(dt_ms),
        }
