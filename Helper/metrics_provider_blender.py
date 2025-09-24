from .metrics_provider import TrackingMetrics, MetricsProvider
import time
import statistics
from typing import Optional
import os
from pathlib import Path


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

    def _log(self, msg: str) -> None:
        """Optional logging helper. Enabled when environment variable
        METRICS_PROVIDER_VERBOSE is set to a truthy value. Logs are appended to
        a file in the user's home directory for easier inspection from Blender.
        """
        try:
            if not os.environ.get("METRICS_PROVIDER_VERBOSE"):
                return
            p = Path(os.path.expanduser(os.environ.get("METRICS_PROVIDER_LOG", "~/.tracking_metrics_provider.log"))).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            # never raise from logging
            pass

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
            self._log(f"no bpy/clip available -> fallback metrics: {out}")
            return out

        tracks = getattr(getattr(clip, "tracking", None), "tracks", None)
        if not tracks:
            dt_ms = (time.time() - t0) * 1000.0
            fallback["time_ms"] = float(dt_ms)
            out = {k: float(v) if isinstance(v, (int, float)) else v for k, v in fallback.items()}
            self._log(f"no tracks on clip -> fallback metrics: {out}")
            return out

        # Determine clip frame offset (Blender movieclip frames are clip-relative)
        try:
            f0 = int(getattr(clip, "frame_start", 1) or 1)
        except Exception:
            f0 = 1
        # convert global/frame to clip-local index
        try:
            clip_idx = int(frame) - int(f0)
        except Exception:
            clip_idx = int(frame) - f0
        # keep a diagnostic view of requested vs local
        try:
            self._log(f"frame mapping: requested_frame={frame} clip_start={f0} clip_idx={clip_idx}")
        except Exception:
            pass

        # Resolve roi_id -> track (index or name)
        track = None
        try:
            roi_idx = int(roi_id)
            if 0 <= roi_idx < len(tracks):
                track = tracks[roi_idx]
        except Exception:
            pass

        if track is None:
            # Try to find a track with a custom roi_id property (if orchestrator annotated it)
            for t in tracks:
                try:
                    v = None
                    # try attribute, dict-like access, or indexing
                    try:
                        v = getattr(t, "roi_id", None)
                    except Exception:
                        v = None
                    if v is None:
                        try:
                            v = t.get("roi_id", None)
                        except Exception:
                            v = None
                    # tolerant comparison: try int/str/float
                    if v is not None:
                        try:
                            if str(int(v)) == str(int(roi_id)):
                                track = t
                                break
                        except Exception:
                            try:
                                if str(v) == str(roi_id):
                                    track = t
                                    break
                            except Exception:
                                pass
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

        # Additional fallback: use marker_refs from online state (registered after seeding)
        # If online state provides marker_refs, prefer aggregating over those named tracks
        try:
            from .tracking_online import get_online_state
            try:
                st = get_online_state(int(roi_id)) if roi_id is not None else {}
            except Exception:
                st = {}
        except Exception:
            st = {}

        marker_refs = list(st.get("marker_refs", []) or [])
        if marker_refs:
            # Build list of tracks referenced by name and aggregate simple metrics across them
            agg_tracks = []
            try:
                for name in marker_refs:
                    try:
                        for t in tracks:
                            try:
                                if getattr(t, "name", None) == name:
                                    agg_tracks.append(t)
                                    break
                            except Exception:
                                continue
                    except Exception:
                        continue
            except Exception:
                agg_tracks = []

            # If we found aggregated tracks, compute presence/corr/jump across them and return early
            if agg_tracks:
                try:
                    markers_total = 0
                    markers_present = 0
                    corrs = []
                    jumps = []
                    residuals = []
                    for t in agg_tracks:
                        try:
                            tmarkers = list(getattr(t, "markers") or []) if hasattr(t, "markers") else list(getattr(t, "tracked_points") or [])
                        except Exception:
                            tmarkers = []
                        markers_total += len(tmarkers)
                        # find marker matching frame idx or nearest
                        for m in tmarkers:
                            try:
                                mf = int(getattr(m, "frame", -999999))
                            except Exception:
                                continue
                            if abs(mf - clip_idx) <= 1 or abs(mf - frame) <= 1:
                                markers_present += 1
                                try:
                                    corrs.append(float(getattr(m, "correlation", getattr(m, "corr", 0.0) or 0.0)))
                                except Exception:
                                    pass
                                # compute simple jump using co if possible vs previous
                                try:
                                    # previous marker in this track
                                    prevs = [pm for pm in tmarkers if int(getattr(pm, "frame", 0)) < int(mf)]
                                    if prevs:
                                        prev = prevs[-1]
                                        co1 = getattr(prev, "co", None) or getattr(prev, "pos", None)
                                        co2 = getattr(m, "co", None) or getattr(m, "pos", None)
                                        if co1 is not None and co2 is not None:
                                            w = getattr(clip, "size", None) or getattr(clip, "resolution", None)
                                            if w and isinstance(w, (tuple, list)) and len(w) >= 2:
                                                sx = w[0]
                                                sy = w[1]
                                            else:
                                                sx = sy = 1.0
                                            dx = (co1[0] - co2[0]) * sx
                                            dy = (co1[1] - co2[1]) * sy
                                            jumps.append((dx * dx + dy * dy) ** 0.5)
                                except Exception:
                                    pass
                        try:
                            residuals.append(float(getattr(t, "error", getattr(t, "average_error", 0.0) or 0.0)))
                        except Exception:
                            pass

                    # Compose aggregated output
                    try:
                        markers_total = int(markers_total or 0)
                    except Exception:
                        markers_total = 0
                    try:
                        markers_present = int(markers_present or 0)
                    except Exception:
                        markers_present = 0

                    if markers_total > 0:
                        lost_rate = float(max(0.0, min(1.0, 1.0 - (markers_present / float(markers_total)))))
                    else:
                        lost_rate = 0.0 if markers_present > 0 else 1.0

                    corr_val = float(statistics.median(corrs)) if corrs else (1.0 / (1.0 + (statistics.median(residuals) if residuals else 0.0)))
                    jump_px = float(statistics.median(jumps)) if jumps else 0.0
                    residual_px = float(statistics.median(residuals)) if residuals else 0.0
                    dt_ms = (time.time() - t0) * 1000.0
                    out = {
                        "corr": float(max(0.0, min(1.0, corr_val or 0.0))),
                        "residual_px": float(residual_px or 0.0),
                        "lost": False if markers_present > 0 else True,
                        "jump_px": float(jump_px or 0.0),
                        "scale_delta": 0.0,
                        "rot_delta": 0.0,
                        "time_ms": float(dt_ms),
                        "_markers_total": markers_total,
                        "_markers_present": markers_present,
                        "_lost_rate": float(lost_rate),
                        "per_marker": [],
                    }
                    # populate per_marker entries if we have any samples (limit to first 100)
                    if markers_present > 0:
                        try:
                            per = []
                            for t in agg_tracks:
                                try:
                                    tmarkers = list(getattr(t, "markers") or []) if hasattr(t, "markers") else list(getattr(t, "tracked_points") or [])
                                except Exception:
                                    tmarkers = []
                                for m_ in tmarkers:
                                    try:
                                        mf = int(getattr(m_, "frame", -999999))
                                    except Exception:
                                        continue
                                    if abs(mf - clip_idx) <= 1 or abs(mf - frame) <= 1:
                                        try:
                                            # Provide both clip-local and global frame values to
                                            # make any frame-offset mapping explicit for callers.
                                            frame_clip = int(mf)
                                            # Many Blender clips store marker.frame as clip-local
                                            # indices; derive a global frame estimate by adding
                                            # the clip start offset `f0` computed earlier.
                                            try:
                                                frame_global = int(frame_clip + int(f0))
                                            except Exception:
                                                frame_global = int(frame_clip)
                                            per.append({
                                                "ref": getattr(t, "name", None),
                                                "frame_clip": frame_clip,
                                                "frame_global": frame_global,
                                                "mapped_idx": int(clip_idx),
                                                "corr": float(getattr(m_, "correlation", getattr(m_, "corr", 0.0) or 0.0)),
                                                "jump_px": float(0.0),
                                                "lost": bool(getattr(m_, "hide", False) or getattr(m_, "mute", False) or getattr(m_, "disabled", False)),
                                            })
                                        except Exception:
                                            continue
                                    if len(per) >= 100:
                                        break
                                if len(per) >= 100:
                                    break
                            out["per_marker"] = per
                        except Exception:
                            pass
                    try:
                        self._log(f"aggregated fetched metrics for roi_id={roi_id} frame={frame} clip_idx={clip_idx} markers_present={markers_present} markers_total={markers_total} -> {out}")
                    except Exception:
                        pass
                    return out
                except Exception:
                    # fallback to normal per-track handling below
                    pass

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
            # Warn once per missing-track incident to make wiring issues visible
            try:
                self._log(f"WARN: track not found for roi_id={roi_id} frame={frame} -> fallback: {out}")
            except Exception:
                pass
            return out

        # Try to extract per-frame marker and metrics (best-effort)
        corr = 0.0
        residual_px = 0.0
        lost = False
        jump_px = 0.0
        scale_delta = 0.0
        rot_delta = 0.0

        # Compute markers_total for this ROI scope (approx.)
        try:
            markers_total = 0
            # If online state registered marker_refs use that
            try:
                from .tracking_online import get_online_state
                st = get_online_state(int(roi_id)) if roi_id is not None else {}
                mr = list(st.get("marker_refs", []) or [])
                markers_total = len(mr) if mr else 0
            except Exception:
                markers_total = 0
        except Exception:
            markers_total = 0

        try:
            # Tracks may expose their marker list as `markers` or `tracked_points`; we also try track.markers.find_frame if available
            markers = []
            if hasattr(track, "markers"):
                try:
                    markers = list(getattr(track, "markers") or [])
                except Exception:
                    markers = []
            else:
                try:
                    markers = list(getattr(track, "tracked_points") or [])
                except Exception:
                    markers = []

            # Find marker by clip-local index if possible (Blender markers store absolute frame numbers sometimes clip-relative)
            marker = None
            # Prefer dedicated API if available
            try:
                if hasattr(track, "markers") and hasattr(track.markers, "find_frame"):
                    # find_frame expects clip-local frame index in many Blender versions
                    try:
                        marker = track.markers.find_frame(int(clip_idx))
                    except Exception:
                        # fallback to requesting with global frame
                        try:
                            marker = track.markers.find_frame(int(frame))
                        except Exception:
                            marker = None
            except Exception:
                marker = None

            # Fallback: search nearest marker by comparing stored marker.frame values against clip-local idx and global frame
            if marker is None and markers:
                best = None
                best_dist = None
                for m in markers:
                    try:
                        mf = int(getattr(m, "frame", -999999))
                        # consider both clip-local and global frame numbers
                        for cand in (mf, mf + f0, mf - f0, frame, clip_idx):
                            try:
                                dist = abs(int(cand) - int(clip_idx))
                                if best_dist is None or dist < best_dist:
                                    best_dist = dist
                                    best = m
                            except Exception:
                                continue
                    except Exception:
                        continue
                marker = best

            if marker is None:
                # marker missing for this frame -> log diagnostic info
                try:
                    mf = []
                    for m in markers:
                        try:
                            mf.append({
                                'frame': int(getattr(m, 'frame', -999999)),
                                'corr': float(getattr(m, 'correlation', getattr(m, 'corr', 0.0) or 0.0)),
                            })
                        except Exception:
                            continue
                    self._log(f"DIAG: no marker at requested_frame={frame} clip_idx={clip_idx} for track={getattr(track,'name',None)} roi_id={roi_id} markers_count={len(markers)} marker_frames={mf}")
                except Exception:
                    pass

            # compute simple presence counts for telemetry
            try:
                markers_present = 0
                if markers:
                    for m in markers:
                        try:
                            mf = int(getattr(m, 'frame', -999999))
                        except Exception:
                            continue
                        # match if close to idx or to global frame
                        if abs(mf - clip_idx) <= 1 or abs(mf - frame) <= 1:
                            markers_present += 1
                # if markers_total unknown, approximate by number of markers in online marker_refs or markers length
                if markers_total == 0:
                    markers_total = len(markers) if markers else markers_total
            except Exception:
                markers_present = 0

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

        # Post-process aggregated telemetry values and ensure non-empty minimal output
        dt_ms = (time.time() - t0) * 1000.0

        # lost_rate and presence
        try:
            markers_total = int(markers_total or 0)
        except Exception:
            markers_total = 0
        try:
            markers_present = int(markers_present or 0)
        except Exception:
            markers_present = 0

        if markers_total > 0:
            try:
                lost_rate = float(max(0.0, min(1.0, 1.0 - (markers_present / float(markers_total)))))
            except Exception:
                lost_rate = 1.0
        else:
            # if we have no total estimate, assume lost if no present markers
            lost_rate = 0.0 if markers_present > 0 else 1.0

        # corr proxy if missing: use inverse residual or 1/(1+residual_px)
        try:
            corr_val = float(max(0.0, min(1.0, corr or (1.0 / (1.0 + float(residual_px or 0.0))))))
        except Exception:
            corr_val = float(max(0.0, min(1.0, corr or 0.0)))

        out = {
            "corr": corr_val,
            "residual_px": float(residual_px or 0.0),
            "lost": bool(lost) or (markers_present == 0 and markers_total > 0),
            "jump_px": float(jump_px or 0.0),
            "scale_delta": float(scale_delta or 0.0),
            "rot_delta": float(rot_delta or 0.0),
            "time_ms": float(dt_ms),
            # additional diagnostics (not part of TrackingMetrics shape strictly,
            # but helpful in logs; callers should ignore unknown keys).
            "_markers_total": markers_total,
            "_markers_present": markers_present,
            "_lost_rate": float(lost_rate),
            "per_marker": [],
        }
        # populate a simple per_marker entry when we detected a marker
        try:
            if markers_present > 0:
                per = []
                # if we have a single `marker` object from above, add it
                try:
                    if marker is not None:
                        try:
                            mf = int(getattr(marker, "frame", frame))
                        except Exception:
                            mf = int(frame)
                        # As above, produce both clip-local and global frame values
                        try:
                            frame_clip = int(mf)
                            frame_global = int(frame_clip + int(f0))
                        except Exception:
                            frame_clip = int(mf)
                            frame_global = int(mf)
                        per.append({
                            "ref": getattr(track, "name", None),
                            "frame_clip": frame_clip,
                            "frame_global": frame_global,
                            "mapped_idx": int(clip_idx),
                            "corr": float(getattr(marker, "correlation", getattr(marker, "corr", 0.0) or 0.0)),
                            "jump_px": float(jump_px or 0.0),
                            "lost": bool(getattr(marker, "hide", False) or getattr(marker, "mute", False) or getattr(marker, "disabled", False)),
                        })
                except Exception:
                    pass
                out["per_marker"] = per
        except Exception:
            pass
        try:
            # Log concise fetch summary
            self._log(f"fetched metrics for roi_id={roi_id} frame={frame} clip_idx={idx} markers_present={markers_present} markers_total={markers_total} -> {out}")
        except Exception:
            pass
        return out
