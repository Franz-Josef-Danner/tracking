from __future__ import annotations

import json
import time
from typing import List, Optional, Sequence

import bpy
from bpy.types import Context, Operator
try:  # NumPy optional
    import numpy as np
except Exception:  # Fallback ohne NumPy
    np = None

def _isfinite(v: float) -> bool:
    return bool(np.isfinite(v)) if np else (v == v and abs(v) != float("inf"))

def _median(vals):
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])

def _percentile(vals, p):
    s = sorted(vals)
    if not s:
        return float("nan")
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)

# --- Debug-Schalter: temporär aktivieren, um nach REFINE hart zu stoppen ---
DEBUG_STOP_AFTER_REFINE = False

__all__ = (
    "CLIP_OT_refine_high_error",
    "run_refine_on_high_error",
    "compute_high_error_frames",
)

# -----------------------------------------------------------------------------
# Kontext-Utilities
# -----------------------------------------------------------------------------

def _clip_override(context: Context) -> Optional[dict]:
    """Ermittelt einen Override-Dict für den CLIP_EDITOR (inkl. window/screen)."""
    win = getattr(context, "window", None)
    scr = getattr(win, "screen", None) if win else None
    if not win or not scr:
        return None
    for area in scr.areas:
        if area.type == "CLIP_EDITOR":
            for region in area.regions:
                if region.type == "WINDOW":
                    return {
                        "window": win,
                        "screen": scr,
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                    }
    return None

# -----------------------------------------------------------------------------
# Frame-Selection Helpers
# -----------------------------------------------------------------------------

def _get_active_clip(context: Context):
    """Ermittelt die aktive MovieClip."""
    # explizite Wahl per Scene-Key zuerst
    scn = getattr(context, "scene", None)
    name = scn.get("refine_clip_name") if scn else None
    if name and name in bpy.data.movieclips:
        return bpy.data.movieclips[name]
    # dann aktiver CLIP_EDITOR (falls vorhanden)
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _scene_to_clip_frame(context, clip, scene_frame: int) -> int:
    """Mappt Szene-Frame deterministisch auf Clip-Frame (ohne UI-Abhängigkeit)."""
    scn = context.scene
    scene_start = int(getattr(scn, "frame_start", 1))
    clip_start = int(getattr(clip, "frame_start", 1))
    scn_fps = float(getattr(getattr(scn, "render", None), "fps", 0) or 0) or 0.0
    clip_fps = float(getattr(clip, "fps", 0) or 0.0)
    scale = 1.0
    if scn_fps > 0.0 and clip_fps > 0.0 and abs(scn_fps - clip_fps) > 1e-3:
        scale = clip_fps / scn_fps
    rel = (scene_frame - scene_start) * scale
    f = int(round(clip_start + rel))
    dur = int(getattr(clip, "frame_duration", 0) or 0)
    if dur > 0:
        fmin, fmax = clip_start, clip_start + dur - 1
        f = max(fmin, min(f, fmax))
    return f


def _debug_mapping_probe(context: Context, n: int = 5) -> None:
    """Gibt eine kurze Szene→Clip-Mapping-Tabelle für Debug-Zwecke aus."""
    clip = _get_active_clip(context)
    scn = context.scene
    name = clip.name if clip else None
    print(f"[DBG] clip={name}, scene_range={scn.frame_start}..{scn.frame_end}")
    end = min(scn.frame_start + n, scn.frame_end + 1)
    for f in range(scn.frame_start, end):
        fc = _scene_to_clip_frame(context, clip, f) if clip else None
        print(f"[DBG] scene {f} -> clip {fc}")

def _find_marker_on_frame(track, frame: int):
    """Sucht einen Marker eines Tracks auf einem spezifischen Frame."""
    for m in track.markers:
        if int(getattr(m, "frame", 0)) == int(frame):
            return m
    return None


def _ref_frame_of_track(track) -> Optional[int]:
    """Frühester Marker-Frame des Tracks (als Referenz)."""
    try:
        return min(m.frame for m in track.markers) if track.markers else None
    except Exception:
        return None


def _keep_only_selection(context: Context, tracks, frame_scene: int, ovr: dict | None):
    """Nur gegebene Tracks + deren Marker auf 'frame_scene' selektieren."""
    clip = _get_active_clip(context)
    if not clip:
        return

    frame_clip = _scene_to_clip_frame(context, clip, frame_scene)

    # Deselect all
    if ovr:
        try:
            with context.temp_override(**ovr):
                bpy.ops.clip.select_all(action='DESELECT')
        except Exception:
            for tr in clip.tracking.tracks:
                tr.select = False
                for m in tr.markers:
                    m.select = False
    else:
        for tr in clip.tracking.tracks:
            tr.select = False
            for m in tr.markers:
                m.select = False
    # Select only requested
    for tr in tracks:
        mk = _find_marker_on_frame(tr, frame_clip)
        if mk:
            tr.select = True
            mk.select = True

def _robust_score(errors: List[float]) -> float:
    """Kombiniert Median und 95. Perzentil zu einem robusten Score."""
    if not errors:
        return float("-inf")
    if np:
        arr = np.asarray(errors, dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            return float("-inf")
        med = float(np.median(arr))
        p95 = float(np.percentile(arr, 95))
    else:
        finite = [v for v in errors if _isfinite(v)]
        if not finite:
            return float("-inf")
        med = float(_median(finite))
        p95 = float(_percentile(finite, 95))
    return 0.7 * p95 + 0.3 * med

def _frame_error(context: Context, frame_scene: int) -> float:
    """Robuster Reprojektion-Score eines Scene-Frames (Median/95p-Mix)."""
    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return float("-inf")

    frame_clip = _scene_to_clip_frame(context, clip, frame_scene)

    values: List[float] = []
    for track in clip.tracking.tracks:
        try:
            marker = _find_marker_on_frame(track, frame_clip)
            if not marker:
                continue
            err = getattr(marker, "error", None)
            if err is None:
                continue
            v = float(err)
            if _isfinite(v):
                values.append(v)
        except Exception:
            pass
    if len(values) < int(getattr(context.scene, "refine_min_markers", 10)):
        return float("-inf")
    return _robust_score(values)

def compute_high_error_frames(context: Context, threshold: float) -> List[int]:
    """
    Liefert problematische Frames.
    Wenn scene['refine_px_thresh'] gesetzt ist → absolute px-Schwelle.
    Sonst → schlechteste max_frac (default 15%) per robustem Score.
    Optional: refine_limit_frames erweitert um ein Fenster.
    """
    scn = context.scene
    preset = scn.get("refine_frames_json")
    if preset:
        try:
            frames = json.loads(preset)
            return [int(f) for f in frames]
        except Exception:
            pass

    fstart, fend = scn.frame_start, scn.frame_end
    frames_all = list(range(fstart, fend + 1))
    scores = [(f, _frame_error(context, f)) for f in frames_all]

    max_frac = float(scn.get("refine_max_frac", 0.15))
    min_frames = int(scn.get("refine_min_frames", 30))
    px_thresh = scn.get("refine_px_thresh", None)
    try:
        px_thresh = float(px_thresh) if px_thresh is not None else None
    except Exception:
        px_thresh = None

    if px_thresh is not None:
        selected = [f for f, s in scores if _isfinite(s) and s >= px_thresh]
    else:
        finite_scores = [kv for kv in scores if _isfinite(kv[1])]
        scores_sorted = sorted(finite_scores, key=lambda kv: kv[1], reverse=True)
        k = max(min_frames, int(len(scores_sorted) * max_frac))
        selected = [f for f, _ in scores_sorted[:k]]

    win = int(scn.get("refine_limit_frames", 0))  # 0 = aus
    if win > 0:
        expanded: set[int] = set()
        for f in selected:
            for g in range(f - win, f + win + 1):
                if fstart <= g <= fend:
                    expanded.add(g)
        selected = sorted(expanded)

    return [int(f) for f in selected]

def _dataset_error_summary(context: Context) -> dict:
    """Grober Before/After-Überblick über die Sequenz."""
    scn = context.scene
    frames = list(range(scn.frame_start, scn.frame_end + 1))
    vals = [_frame_error(context, f) for f in frames]
    finite = [v for v in vals if _isfinite(v)]
    if not finite:
        return {"median": float("inf"), "p95": float("inf"), "mean": float("inf")}
    if np:
        arr = np.asarray(finite, dtype=float)
        return {
            "median": float(np.median(arr)),
            "p95": float(np.percentile(arr, 95)),
            "mean": float(np.mean(arr)),
        }
    return {
        "median": float(_median(finite)),
        "p95": float(_percentile(finite, 95)),
        "mean": float(sum(finite) / len(finite)),
    }

def _select_bad_markers_on_frame(
    context: Context, frame_scene: int, px_thresh: float, ovr: dict | None = None
):
    """
    Deselect all, suche Marker mit Fehler >= px_thresh und gruppiere nach Richtung.
    Rückgabe: (Anzahl, forward_tracks, backward_tracks).
    """
    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return 0, [], []

    frame_clip = _scene_to_clip_frame(context, clip, frame_scene)

    # Sauberes Deselektieren (wie gehabt)
    if ovr:
        try:
            with context.temp_override(**ovr):
                bpy.ops.clip.select_all(action='DESELECT')
        except Exception:
            for tr in clip.tracking.tracks:
                tr.select = False
                for m in tr.markers:
                    m.select = False
    else:
        for tr in clip.tracking.tracks:
            tr.select = False
            for m in tr.markers:
                m.select = False

    fwd, bwd = [], []
    for tr in clip.tracking.tracks:
        mk = _find_marker_on_frame(tr, frame_clip)
        if not mk:
            continue
        err = getattr(mk, "error", None)
        try:
            v = float(err) if err is not None else None
        except Exception:
            v = None
        if v is None or not _isfinite(v):
            continue
        if v >= px_thresh:
            ref_f = _ref_frame_of_track(tr)
            if ref_f is None:
                continue
            (fwd if frame_clip >= ref_f else bwd).append((v, tr))

    # ggf. auf schlechteste N beschränken
    max_sel = int(getattr(context.scene, "refine_max_sel_per_frame", 0))

    def _cap(lst):
        if max_sel > 0 and len(lst) > max_sel:
            lst.sort(key=lambda t: t[0], reverse=True)
            return lst[:max_sel]
        return lst

    fwd = _cap(fwd)
    bwd = _cap(bwd)
    # Rückgabe: Anzahlen + reine Track-Listen
    return len(fwd) + len(bwd), [t for _, t in fwd], [t for _, t in bwd]

# -----------------------------------------------------------------------------
# Modal Operator
# -----------------------------------------------------------------------------

class CLIP_OT_refine_high_error(Operator):
    """Refine High Error (Modal)."""

    bl_idname = "clip.refine_high_error"
    bl_label = "Refine High Error (Modal)"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    _timer: Optional[bpy.types.Timer] = None
    _frames: List[int]
    _idx: int = 0
    _threshold: float = 0.0
    _px_for_selection: float = 0.0  # robuste Auswahl-Schwelle

    def invoke(self, context: Context, event):
        scn = context.scene

        # Mutex-Schutz
        if scn.get("bidi_active") or scn.get("solve_active"):
            self.report({"WARNING"}, "Busy: tracking/solve active")
            return {"CANCELLED"}

        frames_json = scn.get("refine_frames_json", "[]")
        try:
            self._frames = json.loads(frames_json) or []
        except Exception:
            self._frames = []

        if not self._frames:
            self.report({"INFO"}, "No frames to refine")
            scn["refine_result"] = "FINISHED"
            scn["refine_active"] = False
            return {"CANCELLED"}

        self._threshold = float(
            scn.get("refine_threshold", float(getattr(scn, "error_track", 0.0)) * 10.0)
        )
        # Auswahl-Schwelle: nutze 'refine_px_thresh' wenn gesetzt, sonst fallback auf threshold
        self._px_for_selection = float(scn.get("refine_px_thresh", self._threshold))

        wm = context.window_manager
        step_ms = int(scn.get("refine_step_ms", 10))
        self._timer = wm.event_timer_add(step_ms / 1000.0, window=context.window)
        wm.modal_handler_add(self)

        scn["refine_active"] = True
        scn["refine_result"] = ""
        scn.pop("refine_error_msg", None)
        self._idx = 0
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event):
        if event.type == "ESC":
            return self._finish(context, "CANCELLED")
        if event.type == "TIMER":
            try:
                if self._idx >= len(self._frames):
                    return self._finish(context, "FINISHED")

                frame = self._frames[self._idx]
                context.scene.frame_set(frame)

                ovr = _clip_override(context)

                # 1) Auswahl schlechter Marker auf diesem Frame
                def _run_refine(backwards: bool) -> None:
                    if ovr:
                        with context.temp_override(**ovr):
                            bpy.ops.clip.refine_markers('EXEC_DEFAULT', backwards=backwards)
                    else:
                        bpy.ops.clip.refine_markers('EXEC_DEFAULT', backwards=backwards)

                n_sel, fwd_tracks, bwd_tracks = _select_bad_markers_on_frame(
                    context, frame, self._px_for_selection, ovr
                )
                print(
                    f"[Refine] frame={frame} selected={n_sel} "
                    f"th={self._px_for_selection:.2f}"
                )
                if n_sel == 0 and (self._idx % 25 == 0):
                    print(
                        f"[Refine] frame={frame}: nothing above threshold "
                        f"{self._px_for_selection:.2f}px"
                    )
                if n_sel > 0:
                    # forward-Gruppe
                    if fwd_tracks:
                        _keep_only_selection(context, fwd_tracks, frame, ovr)
                        _run_refine(backwards=False)
                    # backward-Gruppe
                    if bwd_tracks:
                        _keep_only_selection(context, bwd_tracks, frame, ovr)
                        _run_refine(backwards=True)

                self._idx += 1
                if self._idx % 25 == 0 or self._idx == len(self._frames):
                    ts = time.strftime('%H:%M:%S')
                    print(f'[{ts}] [Refine] Progress: {self._idx}/{len(self._frames)}')
            except Exception as ex:
                context.scene["refine_error_msg"] = str(ex)
                return self._finish(context, "ERROR")
        return {"PASS_THROUGH"}

    def _finish(self, context: Context, result: str):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

        scn = context.scene
        scn["refine_result"] = result
        scn["refine_active"] = False

        # After-Metrics
        try:
            base = json.loads(scn.pop("refine_baseline_json", "{}") or "{}")
            after = _dataset_error_summary(context)
            def _fmt(k):
                b = base.get(k, after[k])
                return f"{after[k]:.2f}px (Δ {after[k]-b:+.2f})"
            print(
                "[Refine] after: "
                f"median={_fmt('median')}, p95={_fmt('p95')}, mean={_fmt('mean')}"
            )
        except Exception:
            pass

        # --- Debug: Abschluss-Logging + optionaler Hard-Stop NACH refine ---
        print(f"[Refine] _finish(): result={result!r}")
        if DEBUG_STOP_AFTER_REFINE and result in {"FINISHED", "ERROR"}:
            print("[Refine] DEBUG_STOP_AFTER_REFINE aktiv – breche jetzt ab, "
                  "um nachfolgende Logs zu verhindern.")
            raise RuntimeError("[Refine] DEBUG STOP after refine (_finish)")

        return {"FINISHED"} if result == "FINISHED" else {"CANCELLED"}

# -----------------------------------------------------------------------------
# Convenience Wrapper
# -----------------------------------------------------------------------------

def _preview(seq, n=10):
    seq = list(seq)
    return seq[:n] + (['...'] if len(seq) > n else [])

def run_refine_on_high_error(
    context: Context,
    frames: Optional[Sequence[int]] = None,
    threshold: Optional[float] = None,
):
    """Startet den Refine-Modaloperator mit vorbereiteten Scene-Keys."""

    print("\n[Refine] Starte run_refine_on_high_error()")
    print(f"[Refine] Eingabewerte: frames={frames}, threshold={threshold}")

    scn = context.scene
    defaults = {
        "refine_min_markers": 10,
        "refine_px_thresh": 6.0,
        "refine_max_frac": 0.15,
        "refine_min_frames": 30,
        "refine_max_sel_per_frame": 150,
    }
    for k, v in defaults.items():
        if k not in scn:
            scn[k] = v
    if scn.get("bidi_active") or scn.get("solve_active") or scn.get("refine_active"):
        print("[Refine] Busy-Flags aktiv (bidi/solve/refine) – breche Start ab.")
        return {"status": "BUSY"}

    th = (
        float(threshold)
        if threshold is not None
        else float(getattr(scn, "error_track", 0.0)) * 10.0
    )
    print(f"[Refine] threshold (th) = {th}")

    ovr = _clip_override(context)
    if ovr:
        with context.temp_override(**ovr):
            base = _dataset_error_summary(context)
            if frames is None:
                frames = compute_high_error_frames(context, th)
                print(f"[Refine] compute_high_error_frames -> {len(frames)} Frames")
    else:
        base = _dataset_error_summary(context)
        if frames is None:
            frames = compute_high_error_frames(context, th)
            print(f"[Refine] compute_high_error_frames -> {len(frames)} Frames")

    scn["refine_baseline_json"] = json.dumps(base)
    print(
        f"[Refine] baseline: median={base['median']:.2f}px, p95={base['p95']:.2f}px, mean={base['mean']:.2f}px"
    )

    frames = [int(f) for f in frames]
    print(f"[Refine] Frames (Preview): {_preview(frames)}  (total={len(frames)})")
    if not frames:
        scn["refine_result"] = "FINISHED"
        scn["refine_active"] = False
        scn.pop("refine_baseline_json", None)
        print("[Refine] No frames above threshold; skipping.")
        return {"status": "FINISHED", "frames": []}

    scn["refine_frames_json"] = json.dumps(frames)
    scn["refine_threshold"] = th
    scn["refine_result"] = ""
    scn["refine_active"] = True
    scn.pop("refine_error_msg", None)

    # Blender 4.4: Operator mit temp_override + 'INVOKE_DEFAULT' starten
    if ovr:
        print(f"[Refine] Starte Operator (override, {len(frames)} Frames)...")
        with context.temp_override(**ovr):
            bpy.ops.clip.refine_high_error('INVOKE_DEFAULT')
    else:
        print(f"[Refine] Starte Operator (kein override, {len(frames)} Frames)...")
        bpy.ops.clip.refine_high_error('INVOKE_DEFAULT')

    result = {"status": "STARTED", "frames": frames, "threshold": th}
    print(f"[Refine] Operator gestartet -> {result}")
    # Hinweis: Der Hard-Stop erfolgt NACH dem Refine in _finish(), nicht hier!
    return result

# -----------------------------------------------------------------------------
# Register
# -----------------------------------------------------------------------------

_classes = (CLIP_OT_refine_high_error,)

def register() -> None:
    from bpy.utils import register_class

    for cls in _classes:
        register_class(cls)

def unregister() -> None:
    from bpy.utils import unregister_class

    for cls in reversed(_classes):
        unregister_class(cls)
