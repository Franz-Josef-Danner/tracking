# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import time
import math
import bpy
from bpy.types import Scene
from bpy.props import BoolProperty, FloatProperty, IntProperty
from typing import Optional, Dict, Any, Callable, Tuple

# Entfernt: Triplet-Grouping/Joiner aus dem Ablauf
# Entfernt: parallax_keyframe (Helper/parallax_keyframe.py) vollständig aus Pipeline
# from ..Helper.triplet_grouping import run_triplet_grouping  # removed
from ..Helper.projection_cleanup_builtin import run_projection_cleanup_builtin
from ..Helper.projektion_spike_filter_cycle import run_projection_spike_filter_cycle  # NEW
from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
from ..Helper.find_max_marker_frame import run_find_max_marker_frame  # type: ignore
from ..Helper.spike_filter_cycle import run_marker_spike_filter_cycle  # type: ignore
from ..Helper.split_cleanup import recursive_split_cleanup  # type: ignore
from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

# Scene Keys
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8

_last_solve_error: Optional[float] = None
_same_error_repeat_count: int = 0

_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"

# Keys für Optimizer-Signal (werden von Helper/jump_to_frame.py gesetzt)
_OPT_REQ_KEY = "__optimize_request"
_OPT_REQ_VAL = "JUMP_REPEAT"
_OPT_FRAME_KEY = "__optimize_frame"

# Default-Parameter
_DEFAULT_SOLVE_WAIT_S = 60.0
_DEFAULT_REFINE_POLL_S = 0.05
_DEFAULT_SPIKE_START = 20

# Maximal erlaubte Anzahl an FIND_MAX↔SPIKE-Iterationen
# Hinweis: Zähler beginnt erst, wenn ein Spike-Iteration tatsächlich Marker entfernt hat.
_CYCLE_MAX_ITER = 6


def _tco_log(msg: str) -> None:
    print(f"[tracking_coordinator] {msg}")


def _pause(seconds: float = 0.5) -> None:
    """Kleine, robuste Pause zwischen Schritten."""
    try:
        time.sleep(float(seconds))
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_call(func: Callable[..., Any], *args, **kwargs) -> Tuple[bool, Any]:
    try:
        return True, func(*args, **kwargs)
    except Exception as ex:  # noqa: BLE001
        _tco_log(f"_safe_call({getattr(func, '__name__', 'func')}): {ex!r}")
        return False, ex


def _safe_ops_invoke(ops_path: str, *args, **kwargs) -> Tuple[bool, Any]:
    try:
        mod, name = ops_path.split(".", 1)
        op = getattr(getattr(bpy.ops, mod), name)
    except Exception as ex:  # noqa: BLE001
        _tco_log(f"_safe_ops_invoke: resolve failed for '{ops_path}': {ex!r}")
        return False, ex
    try:
        return True, op(*args, **kwargs)
    except Exception as ex:  # noqa: BLE001
        _tco_log(f"_safe_ops_invoke: call failed for '{ops_path}': {ex!r}")
        return False, ex


def _scene_float(scene: bpy.types.Scene, key: str, default: float) -> float:
    try:
        v = getattr(scene, key, default)
        v = default if v is None else v
        return float(v)
    except Exception:
        return float(default)


def _have_clip(context: bpy.types.Context) -> bool:
    space = getattr(context, "space_data", None)
    return bool(getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None))


def _current_solve_error(context: bpy.types.Context) -> Optional[float]:
    """Average-Error aus aktiver Reconstruction (oder None)."""
    space = getattr(context, "space_data", None)
    clip = space.clip if (getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None)) else None
    if clip is None:
        try:
            clip = bpy.data.movieclips[0] if bpy.data.movieclips else None
        except Exception:
            clip = None
    if not clip:
        return None
    try:
        recon = clip.tracking.objects.active.reconstruction
        if not getattr(recon, "is_valid", False):
            return None
        if hasattr(recon, "average_error"):
            return float(recon.average_error)
    except Exception:
        return None
    return None


def _wait_for_valid_reconstruction(
    context: bpy.types.Context, *, timeout_s: float, poll_s: float = 0.05
) -> Optional[float]:
    """Pollt bis valide Reconstruction oder Timeout; liefert avg_error oder None."""
    deadline = time.monotonic() + float(timeout_s)
    while time.monotonic() < deadline:
        err = _current_solve_error(context)
        if err is not None:
            return float(err)
        try:
            time.sleep(float(poll_s))
        except Exception:
            pass
    return None


# ---- Split-Cleanup Helpers (blocking) ----

def _get_active_clip(context: bpy.types.Context):
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _get_tracks_collection(clip):
    try:
        obj = clip.tracking.objects.active
        if obj and getattr(obj, "tracks", None):
            return obj.tracks
    except Exception:
        pass
    try:
        return clip.tracking.tracks
    except Exception:
        return None


def _resolve_clip_editor_area_triplet(context) -> Tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[Any]]:
    """Findet eine CLIP_EDITOR Area/Region/Space-Triplette für Kontext-Overrides."""
    area = None
    region = None
    space = None
    try:
        screen = context.window.screen if context.window else None
        for a in (screen.areas if screen else []):
            if a.type == "CLIP_EDITOR":
                area = a
                region = next((r for r in a.regions if r.type == "WINDOW"), None) or (a.regions[0] if a.regions else None)
                space = a.spaces.active if hasattr(a, "spaces") else None
                if region and space:
                    break
    except Exception:
        pass
    return area, region, space


def _run_split_cleanup_blocking(context: bpy.types.Context) -> None:
    """Führt Helper/split_cleanup.py synchron aus und kehrt erst nach Abschluss zurück."""
    clip = _get_active_clip(context)
    if not clip:
        _tco_log("split_cleanup: no active clip → skipped")
        return

    area, region, space = _resolve_clip_editor_area_triplet(context)
    if not (area and region and space):
        _tco_log("split_cleanup: no CLIP_EDITOR area/region/space → skipped")
        return

    tracks = _get_tracks_collection(clip) or []
    prev_verbose = context.scene.get("tco_verbose_split", False)

    try:
        with context.temp_override(area=area, region=region, space_data=space):
            # sicherstellen, dass der Space auch den gewünschten Clip zeigt
            try:
                if getattr(space, "clip", None) is not clip:
                    space.clip = clip
            except Exception:
                pass

            context.scene["tco_verbose_split"] = True
            res = recursive_split_cleanup(context, area, region, space, tracks)
        _tco_log(f"split_cleanup finished → {res}")
    except Exception as ex:
        _tco_log(f"split_cleanup failed: {ex!r}")
    finally:
        # Verbose-Flag zurücksetzen
        try:
            context.scene["tco_verbose_split"] = bool(prev_verbose)
        except Exception:
            pass

# ---- NEW: Select-All-Tracks (blocking) ----

def _select_all_tracks_blocking(context: bpy.types.Context) -> bool:
    """Selektiert alle Tracks im aktiven Clip (CLIP_EDITOR-Kontext)."""
    clip = _get_active_clip(context)
    if not clip:
        _tco_log("select_all_tracks: no active clip → skipped")
        return False

    area, region, space = _resolve_clip_editor_area_triplet(context)
    if not (area and region and space):
        _tco_log("select_all_tracks: no CLIP_EDITOR area/region/space → skipped")
        return False

    try:
        with context.temp_override(area=area, region=region, space_data=space):
            try:
                if getattr(space, "clip", None) is not clip:
                    space.clip = clip
            except Exception:
                pass

            # Operator ist robust und UI-konform
            ok, _ = _safe_ops_invoke("clip.select_all", action='SELECT')
            if ok:
                _tco_log("select_all_tracks: all tracks selected via clip.select_all(SELECT)")
                return True
            # Fallback: hart selektieren über API
            tracks = _get_tracks_collection(clip) or []
            for t in tracks:
                try:
                    t.select = True
                except Exception:
                    pass
            _tco_log("select_all_tracks: fallback selection done")
            return True
    except Exception as ex:
        _tco_log(f"select_all_tracks failed: {ex!r}")
        return False


# ---------------------------------------------------------------------------
# (Optional) Spike-Value Memo für externe Trigger
# ---------------------------------------------------------------------------

def register_scene_state() -> None:
    if not hasattr(Scene, "tco_spike_value"):
        Scene.tco_spike_value = FloatProperty(
            name="Spike Filter Value",
            description="Gemerkter Wert für spike_filter_cycle (optional).",
            default=0.0,
        )
    if not hasattr(Scene, "tco_spike_pending"):
        Scene.tco_spike_pending = BoolProperty(
            name="Spike Pending",
            description="True, wenn ein Spike-Wert gemerkt wurde und nach Cleanup einmalig ausgelöst wird.",
            default=False,
        )
    if not hasattr(Scene, "spike_start_threshold"):
        Scene.spike_start_threshold = FloatProperty(
            name="Spike Start",
            default=_DEFAULT_SPIKE_START,
            min=0.0,
            description="Startthreshold für Spike-Filter-Zyklus",
        )


def unregister_scene_state() -> None:
    for attr in ("tco_spike_value", "tco_spike_pending", "spike_start_threshold"):
        if hasattr(Scene, attr):
            delattr(Scene, attr)


def remember_spike_filter_value(value: float, *, context: bpy.types.Context | None = None) -> None:
    ctx = context or bpy.context
    scene = ctx.scene
    scene.tco_spike_value = float(value)
    scene.tco_spike_pending = True
    _tco_log(f"remember_spike_filter_value: value={scene.tco_spike_value:.6f}, pending=True")


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """
    Zielablauf:

      A) FIND_LOW findet Frames:
         → JUMP → DETECT → TRACK (bidi) → CLEAN_SHORT → zurück zu FIND_LOW

      B) FIND_LOW liefert NONE:
         → CYCLE_START
         → Unbegrenzt: CYCLE_FIND_MAX; wenn NONE/FAILED → CYCLE_SPIKE; dann zurück zu CYCLE_FIND_MAX
           … bis FIND_MAX einen Frame liefert
         → SOLVE → EVAL
              → wenn OK: FINALIZE
              → wenn nicht: CLEANUP → zurück zu FIND_LOW

    Hinweis: Die Iterationsbegrenzung für FIND_MAX↔SPIKE beginnt erst zu zählen,
    wenn eine SPIKE-Iteration tatsächlich Marker entfernt hat.
    """
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator"
    bl_options = {"REGISTER", "UNDO"}

    use_apply_settings: bpy.props.BoolProperty(  # type: ignore
        name="Apply Tracker Defaults",
        default=True,
    )

    _timer: Optional[bpy.types.Timer] = None
    _state: str = "INIT"
    _detect_attempts: int = 0
    _jump_done: bool = False
    _repeat_map: Dict[int, int]
    _bidi_started: bool = False

    # CYCLE (FIND_MAX ↔ SPIKE)
    _cycle_active: bool = False
    _cycle_target_frame: Optional[int] = None
    _cycle_iterations: int = 0  # neu: Zähler für die Anzahl der Cycle-Iterationen (zählt nur echte Löschaktionen)

    # SPIKE
    _spike_threshold: float = _DEFAULT_SPIKE_START

    # Solve/Eval/Refine
    _pending_eval_after_solve: bool = False
    _did_refine_this_cycle: bool = False

    # --- NEU: Solve-Error-Merker ---
    # Klassenattribute → existieren garantiert, auch falls _bootstrap nicht lief
    _last_solve_error: Optional[float] = None
    _same_error_repeat_count: int = 0

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    # ---------------- Lifecycle ----------------

    def _run_pre_flight_helpers(self, context) -> None:
        # tracker_settings (defensiv)
        try:
            from ..Helper.tracker_settings import apply_tracker_settings  # type: ignore
            ok, res = _safe_call(apply_tracker_settings, context, log=True)
            if ok:
                print("[Coord] BOOTSTRAP → tracker_settings OK")
            else:
                print(f"[Coord] BOOTSTRAP WARN: tracker_settings failed: {res!r}")
                _safe_ops_invoke("clip.apply_tracker_settings", 'INVOKE_DEFAULT')
        except Exception as ex:
            print(f"[Coord] BOOTSTRAP WARN: tracker_settings import failed: {ex!r}")
            _safe_ops_invoke("clip.apply_tracker_settings", 'INVOKE_DEFAULT')

        # marker_helper_main (defensiv)
        try:
            from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
            ok, res = _safe_call(marker_helper_main, context)
            if ok:
                print("[Coord] BOOTSTRAP → marker_helper_main OK")
            else:
                print(f"[Coord] BOOTSTRAP WARN: marker_helper_main failed: {res!r}")
        except Exception as ex_func:  # noqa: BLE001
            print(f"[Coord] BOOTSTRAP WARN: marker_helper_main import failed: {ex_func!r}")
            try:
                bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')
            except Exception:
                pass

        if self.use_apply_settings:
            try:
                from ..Helper.apply_tracker_settings import apply_tracker_settings  # type: ignore
                apply_tracker_settings(context)
                print("[Coord] BOOTSTRAP → apply_tracker_settings() OK")
            except Exception as ex:
                print(f"[Coord] BOOTSTRAP INFO: apply_tracker_settings not available/failed: {ex!r}")

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self._bootstrap(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        print("[Coord] START (Detect/Bidi-Loop; unendlicher CYCLE: FIND_MAX↔SPIKE bis FOUND; Solve→Eval→Cleanup)")
        return {"RUNNING_MODAL"}

    # ---------------- Bootstrap ----------------

    def _bootstrap(self, context):
        scn = context.scene
        scn[_LOCK_KEY] = False
        scn[_BIDI_ACTIVE_KEY] = False
        scn[_BIDI_RESULT_KEY] = ""
        scn.pop(_GOTO_KEY, None)

        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False

        # Cycle reset
        self._cycle_active = False
        self._cycle_target_frame = None
        self._cycle_iterations = 0  # reset counter

        # Spike reset
        self._spike_threshold = float(getattr(scn, "spike_start_threshold", _DEFAULT_SPIKE_START) or _DEFAULT_SPIKE_START)

        # Solve/Eval/Refine
        self._pending_eval_after_solve = False
        self._did_refine_this_cycle = False

        # --- NEU: Solve-Error-Merker zurücksetzen ---
        self._last_solve_error = None
        self._same_error_repeat_count = 0

    # ---------------- States ----------------

    def _state_init(self, context):
        print("[Coord] INIT → BOOTSTRAP")
        self._run_pre_flight_helpers(context)
        print("[Coord] BOOTSTRAP → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _state_find_low(self, context):
        if not _have_clip(context):
            print("[Coord] FIND_LOW → no active clip → retry")
            return {"RUNNING_MODAL"}

        ok, result = _safe_call(run_find_low_marker_frame, context)
        if not ok or not isinstance(result, dict):
            print(f"[Coord] FIND_LOW → FAILED (exception/invalid) → treat as NONE")
            result = {"status": "NONE", "reason": "exception-or-invalid-result"}

        status = str(result.get("status", "NONE")).upper()
        if status == "FOUND":
            frame = int(result.get("frame", context.scene.frame_current))
            context.scene[_GOTO_KEY] = frame
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FOUND frame={frame} → JUMP")
            self._state = "JUMP"
        else:
            # NONE → Zyklus starten
            print("[Coord] FIND_LOW → NONE → CYCLE_START (FIND_MAX↔SPIKE, max iterations: {0})".format(_CYCLE_MAX_ITER))
            self._cycle_active = True
            self._cycle_target_frame = None
            self._cycle_iterations = 0

            # harter Reset für jeden neuen Cycle
            self._spike_threshold = float(
                getattr(context.scene, "spike_start_threshold", _DEFAULT_SPIKE_START) or _DEFAULT_SPIKE_START
            )
            print(f"[Coord] CYCLE_START → reset spike start = {self._spike_threshold:.2f}")

            self._did_refine_this_cycle = False
            self._state = "CYCLE_FIND_MAX"
        return {"RUNNING_MODAL"}

    # ---------------- JUMP/DETECT/TRACK/CLEAN_SHORT ----------------

    def _state_jump(self, context):
        from ..Helper.jump_to_frame import run_jump_to_frame  # type: ignore
        if not self._jump_done:
            goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
            ok, jr = _safe_call(run_jump_to_frame, context, frame=goto, repeat_map=self._repeat_map)
            if not ok or not isinstance(jr, dict) or jr.get("status") != "OK":
                print(f"[Coord] JUMP failed → FIND_LOW")
                self._state = "FIND_LOW"
                return {"RUNNING_MODAL"}

            print(f"[Coord] JUMP → frame={jr['frame']} repeat={jr.get('repeat_count', 0)} → DETECT")

            scn = context.scene
            opt_req = scn.get(_OPT_REQ_KEY, None)
            opt_frame = int(scn.get(_OPT_FRAME_KEY, jr.get('frame', scn.frame_current)))
            if jr.get("optimize_signal") or opt_req == _OPT_REQ_VAL:
                scn.pop(_OPT_REQ_KEY, None)
                scn[_OPT_FRAME_KEY] = opt_frame
                try:
                    from ..Helper.optimize_tracking_modal import start_optimization  # type: ignore
                    if int(context.scene.frame_current) != int(opt_frame):
                        context.scene.frame_set(int(opt_frame))
                    ok_opt, res_opt = _safe_call(start_optimization, context)
                    if ok_opt:
                        print(f"[Coord] JUMP → OPTIMIZE (function, frame={opt_frame})")
                    else:
                        print(f"[Coord] OPTIMIZE failed (function): {res_opt!r}")
                        ok_op, _ = _safe_ops_invoke("clip.optimize_tracking_modal", 'INVOKE_DEFAULT')
                        if ok_op:
                            print(f"[Coord] JUMP → OPTIMIZE (operator, frame={opt_frame})")
                except Exception as ex_func:
                    print(f"[Coord] OPTIMIZE failed: {ex_func!r}")

            self._jump_done = True

        self._detect_attempts = 0
        self._state = "DETECT"
        return {"RUNNING_MODAL"}

    def _state_detect(self, context):
        from ..Helper.detect import run_detect_once  # type: ignore
        goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
        ok, res = _safe_call(run_detect_once, context, start_frame=goto, handoff_to_pipeline=True)
        status = "FAILED" if (not ok or not isinstance(res, dict)) else str(res.get("status", "FAILED")).upper()

        if status == "RUNNING":
            self._detect_attempts += 1
            print(f"[Coord] DETECT → RUNNING ({self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[Coord] DETECT Timebox erreicht → force TRACK")
                self._state = "TRACK"
            return {"RUNNING_MODAL"}

        # Triplet-Grouping vollständig entfernt
        print(f"[Coord] DETECT → {status} → TRACK (bidi)")
        self._state = "TRACK"
        return {"RUNNING_MODAL"}

    def _state_track(self, context):
        scn = context.scene

        if not self._bidi_started:
            scn[_BIDI_ACTIVE_KEY] = False
            print("[Coord] TRACK → launch clip.bidirectional_track (INVOKE_DEFAULT)")
            ok, _ = _safe_ops_invoke("clip.bidirectional_track", 'INVOKE_DEFAULT')
            if ok:
                self._bidi_started = True
            else:
                print("[Coord] TRACK launch failed → CLEAN_SHORT")
                self._bidi_started = False
                self._state = "CLEAN_SHORT"
            return {"RUNNING_MODAL"}

        if scn.get(_BIDI_ACTIVE_KEY, False):
            return {"RUNNING_MODAL"}

        result = str(scn.get(_BIDI_RESULT_KEY, "") or "").upper()
        scn[_BIDI_RESULT_KEY] = ""
        self._bidi_started = False
        print(f"[Coord] TRACK → finished (result={result or 'NONE'}) → CLEAN_SHORT")
        self._state = "CLEAN_SHORT"
        return {"RUNNING_MODAL"}

    def _state_clean_short(self, context):
        try:
            frames_min = int(getattr(context.scene, "frames_track", 25) or 25)
            clean_short_tracks(context, min_len=frames_min, verbose=True)
            print(f"[Coord] CLEAN_SHORT → clean_short_tracks(min_len={frames_min})")
        except TypeError:
            clean_short_tracks(context)
            print("[Coord] CLEAN_SHORT → clean_short_tracks() fallback")
        except Exception as ex:
            print(f"[Coord] CLEAN_SHORT failed: {ex!r}")

        print("[Coord] CLEAN_SHORT → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    # ---------------- CYCLE: FIND_MAX ↔ SPIKE (mit Iterationslimit) ----------------

    def _state_cycle_find_max(self, context):
        if not self._cycle_active:
            print("[Coord] CYCLE_FIND_MAX reached with inactive cycle → FINALIZE")
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}

        print(f"[Coord] CYCLE_FIND_MAX → check (current deletion-iterations={self._cycle_iterations}/{_CYCLE_MAX_ITER})")

        try:
            res = run_find_max_marker_frame(context)
        except Exception as ex:
            print(f"[Coord] CYCLE_FIND_MAX failed: {ex!r}")
            res = {"status": "FAILED", "reason": repr(ex)}

        status = str(res.get("status", "FAILED")).upper()
        if status == "FOUND":
            frame = int(res.get("frame", getattr(context.scene, "frame_current", 0)))
            count = res.get("count", "?")
            thresh = res.get("threshold", "?")
            print(f"[Coord] CYCLE_FIND_MAX → FOUND frame={frame} (count={count} < threshold={thresh})")

            self._cycle_target_frame = frame
            try:
                context.scene.frame_set(frame)
            except Exception as ex_set:
                print(f"[Coord] WARN: frame_set({frame}) failed: {ex_set!r}")

            # Zyklus beenden → erst Split-Cleanup (blocking), dann Segment/Track-Clean, dann Solve
            self._cycle_active = False
            print("[Coord] CYCLE_FIND_MAX → SPLIT_CLEANUP (blocking)")
            _run_split_cleanup_blocking(context)
            _pause(0.5)

            # Nach Split: kurze Segmente entfernen (robust gegen Mutes/Lücken)
            try:
                from ..Helper.clean_short_segments import clean_short_segments  # type: ignore
                seg_min = int(getattr(context.scene, "tco_min_seg_len", 0)) \
                          or int(getattr(context.scene, "frames_track", 0)) or 25
                css_res = clean_short_segments(context, min_len=seg_min, treat_muted_as_gap=True, verbose=True)
                print(f"[Coord] post-SPLIT → clean_short_segments(min_len={seg_min}) → {css_res}")
            except Exception as ex:
                print(f"[Coord] WARN: clean_short_segments failed post-SPLIT: {ex!r}")
            _pause(0.5)

            try:
                frames_min = int(getattr(context.scene, "frames_track", 25) or 25)
                clean_short_tracks(context, min_len=frames_min, verbose=True)
                print(f"[Coord] CYCLE_FIND_MAX → clean_short_tracks(min_len={frames_min})")
            except Exception as ex:
                print(f"[Coord] CLEAN_SHORT (post-split) failed: {ex!r}")
            _pause(0.5)

            print("[Coord] CYCLE_FIND_MAX → SOLVE")
            self._pending_eval_after_solve = True
            self._state = "SOLVE"
            return {"RUNNING_MODAL"}  # ← wichtig!

        # NONE/FAILED → SPIKE
        print(f"[Coord] CYCLE_FIND_MAX → {status} → CYCLE_SPIKE")
        self._state = "CYCLE_SPIKE"
        return {"RUNNING_MODAL"}

    def _state_cycle_spike(self, context):
        if not self._cycle_active:
            ...
        use_proj = bool(list(getattr(context.scene, "tco_proj_spike_tracks", []) or []))
        try:
            if use_proj:
                res = run_projection_spike_filter_cycle(
                    context,
                    track_threshold=float(self._spike_threshold),
                    run_segment_cleanup=False,
                )
                status = str(res.get("status","")).upper()
                muted = int(res.get("deleted", 0) or 0)     # projektion_* meldet "deleted" Marker
            else:
                res = run_marker_spike_filter_cycle(
                    context,
                    track_threshold=float(self._spike_threshold),
                    action="MUTE",
                    run_segment_cleanup=False,
                )
                status = str(res.get("status","")).upper()
                muted = int(res.get("muted", 0) or 0)

            next_thr = float(res.get("next_threshold", self._spike_threshold * 0.9))
            print(f"[Coord] CYCLE_SPIKE → status={status}, affected={muted}, next={next_thr:.2f} (curr={self._spike_threshold:.2f})")
            self._spike_threshold = max(next_thr, 0.0)
            ...

            # **Neu**: segmentweises Clean **nach** dem Spike-Pass (robuster, zentralisiert)
            _pause(0.5)
            try:
                from ..Helper.clean_short_segments import clean_short_segments  # type: ignore
                seg_min = int(getattr(context.scene, "tco_min_seg_len", 0)) \
                          or int(getattr(context.scene, "frames_track", 0)) or 25
                css_res = clean_short_segments(context, min_len=seg_min, treat_muted_as_gap=True, verbose=True)
                print(f"[Coord] CYCLE_SPIKE → clean_short_segments(min_len={seg_min}) → {css_res}")
            except Exception as ex:
                print(f"[Coord] WARN: clean_short_segments failed post-SPIKE: {ex!r}")
            _pause(0.5)

            # Optional: zu kurze **Tracks** kappen (nach Segment-Clean)
            try:
                frames_min = int(getattr(context.scene, "frames_track", 25) or 25)
                clean_short_tracks(context, min_len=frames_min, verbose=True)
                print(f"[Coord] CYCLE_SPIKE → clean_short_tracks(min_len={frames_min})")
            except Exception as ex:
                print(f"[Coord] WARN: clean_short_tracks failed post-SPIKE: {ex!r}")

            if muted > 0:
                self._cycle_iterations += 1
                print(f"[Coord] CYCLE_SPIKE → muted>0 → incremented deletion-iterations to {self._cycle_iterations}/{_CYCLE_MAX_ITER}")
                if self._cycle_iterations > _CYCLE_MAX_ITER:
                    print(f"[Coord] CYCLE deletion-iteration limit ... → SPLIT_CLEANUP (blocking)")
                    self._cycle_active = False
                    _run_split_cleanup_blocking(context)
                    _pause(0.5)

                    # Clean-Short-Tracks
                    # Nach Split: erst Segmente, dann Tracks, dann Solve (mit Pausen)
                    try:
                        from ..Helper.clean_short_segments import clean_short_segments  # type: ignore
                        seg_min = int(getattr(context.scene, "tco_min_seg_len", 0)) \
                                  or int(getattr(context.scene, "frames_track", 0)) or 25
                        css_res = clean_short_segments(context, min_len=seg_min, treat_muted_as_gap=True, verbose=True)
                        print(f"[Coord] post-SPLIT(limit) → clean_short_segments(min_len={seg_min}) → {css_res}")
                    except Exception as ex:
                        print(f"[Coord] WARN: clean_short_segments failed post-SPLIT(limit): {ex!r}")
                    _pause(0.5)

                    # Clean-Short-Tracks
                    try:
                        frames_min = int(getattr(context.scene, "frames_track", 25) or 25)
                        clean_short_tracks(context, min_len=frames_min, verbose=True)
                        print(f"[Coord] CYCLE_SPIKE → clean_short_tracks(min_len={frames_min})")
                    except Exception as ex:
                        print(f"[Coord] CLEAN_SHORT (post-split) failed: {ex!r}")
                    _pause(0.5)

                    print("[Coord] CYCLE_SPIKE → SOLVE")
                    self._pending_eval_after_solve = True
                    self._state = "SOLVE"
                    return {"RUNNING_MODAL"}  # ← wichtig!

        except Exception as ex:
            print(f"[Coord] CYCLE_SPIKE failed: {ex!r}")
            self._state = "CYCLE_FIND_MAX"
            return {"RUNNING_MODAL"}

        # Nächster Schritt im Cycle
        self._state = "CYCLE_FIND_MAX"
        return {"RUNNING_MODAL"}

    # ---------------- SOLVE → EVAL → CLEANUP ----------------

    def _state_eval(self, context):
        target = _scene_float(context.scene, "error_track", 0.0)
        wait_s = _scene_float(context.scene, "solve_wait_timeout_s", _DEFAULT_SOLVE_WAIT_S)

        curr = _wait_for_valid_reconstruction(context, timeout_s=wait_s)
        curr = _current_solve_error(context) if curr is None else curr
        print(f"[Coord] EVAL → curr_error={curr if curr is not None else 'None'} target={target}")
        # --- NEU: zweimal identischer Error → einmalig triggern ---
        # Note: math.isclose statt exakter Gleichheit (floating point!)
        if curr is not None:
            if self._last_solve_error is not None and math.isclose(
                float(curr), float(self._last_solve_error), rel_tol=1e-6, abs_tol=1e-6
            ):
                self._same_error_repeat_count += 1
            else:
                self._same_error_repeat_count = 1  # neuer Wert startet Zählung
            self._last_solve_error = float(curr)

            if self._same_error_repeat_count >= 2:
                print(f"[Coord] EVAL → identischer Solve-Error zweimal in Folge ({curr:.6f}) → Trigger")
                # einmalig auslösen → z. B. Cleanup anstoßen
                self._same_error_repeat_count = 0
                self._last_solve_error = None
                self._state = "CLEANUP"
                return {"RUNNING_MODAL"}

        # --- NEU: Check auf zweimal denselben Error hintereinander ---
        if curr is not None:
            if self._last_solve_error is not None and abs(curr - self._last_solve_error) < 1e-6:
                self._same_error_repeat_count += 1
            else:
                self._same_error_repeat_count = 1  # reset, neuer Wert

            self._last_solve_error = curr

            if self._same_error_repeat_count >= 2:
                print(f"[Coord] EVAL → ERROR {curr:.4f} wiederholt sich zweimal → Trigger ausgelöst")
                self._same_error_repeat_count = 0  # zurücksetzen, nur einmal auslösen
                # >>> HIER deinen gewünschten Effekt starten <<<
                # z. B. sofort in CLEANUP wechseln:
                self._state = "CLEANUP"
                return {"RUNNING_MODAL"}

        if target > 0.0 and curr is not None and curr <= target:            # Direkt zu den finalen Intrinsics-Refinements (parallax_keyframe entfernt)
            print("[Coord] EVAL → OK (≤ target) → performing final intrinsics refinement steps")

            clip = getattr(context.space_data, "clip", None)
            ts = getattr(getattr(clip, "tracking", None), "settings", None)

            def _toggle_attr(container, names, on: bool) -> str | None:
                """Setzt das erste gefundene Attribut auf on/off und liefert den Namen zurück."""
                if not container:
                    return None
                for nm in names:
                    if hasattr(container, nm):
                        try:
                            setattr(container, nm, bool(on))
                            return nm
                        except Exception:
                            continue
                return None

            # 1) Nur Focal-Length verfeinern
            focal_attr = _toggle_attr(ts, (
                "refine_intrinsics_focal_length",
                "refine_focal_length",
                "refine_focal",
            ), True)


            # 2) Focal + Radial Distortion
            radial_attr = _toggle_attr(ts, (
                "refine_intrinsics_radial_distortion",
                "refine_radial_distortion",
                "refine_distortion",
                "refine_k1",
            ), True)

            # 3) Optional: Principal Point
            principal_attr = _toggle_attr(ts, (
                "refine_intrinsics_principal_point",
                "refine_principal_point",
                "refine_principal",
            ), True)

            # Flags wieder ausschalten, damit Standard-Defaults beibehalten werden
            _toggle_attr(ts, ("refine_intrinsics_principal_point","refine_principal_point","refine_principal"), False)
            _toggle_attr(ts, ("refine_intrinsics_radial_distortion","refine_radial_distortion","refine_distortion","refine_k1"), False)
            _toggle_attr(ts, ("refine_intrinsics_focal_length","refine_focal_length","refine_focal"), False)

            print("[Coord] EVAL → final intrinsics refinement done → FINALIZE")
            self._pending_eval_after_solve = False
            self._did_refine_this_cycle = False
            self._state = "FINALIZE"
        else:
            print("[Coord] EVAL → above target → CLEANUP")
            self._state = "CLEANUP"
        return {"RUNNING_MODAL"}

    def _state_cleanup(self, context):
        # 1) Projektionsbasiert selektieren & Track-Namen in Szene persistieren lassen
        ok, res = _safe_call(run_projection_cleanup_builtin, context)
        if ok:
            print(f"[Coord] CLEANUP(select) → {res}")
        else:
            print(f"[Coord] CLEANUP(select) failed: {res!r}")

        _pause(0.5)

        # 2) Spike-Filter nur auf die selektierten (schlechtesten) Tracks anwenden
        try:
            thr = float(getattr(context.scene, "spike_start_threshold", 20.0) or 20.0)
        except Exception:
            thr = 20.0

        ok2, res2 = _safe_call(
            run_projection_spike_filter_cycle,
            context,
            track_threshold=thr,
            run_segment_cleanup=False,   # <— von True auf False
            treat_muted_as_gap=True,
        )

        if ok2:
            print(f"[Coord] CLEANUP(spike) → {res2}")
        else:
            print(f"[Coord] CLEANUP(spike) failed: {res2!r}")

        print("[Coord] CLEANUP → FIND_LOW (back to loop)")
        self._pending_eval_after_solve = False
        self._did_refine_this_cycle = False
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    # ---------------- Modal-Wrapper ----------------
    def modal(self, context, event):
        try:
            if event.type == "ESC":
                return self._finish(context, cancelled=True)
            if event.type != "TIMER":
                return {"PASS_THROUGH"}

            if context.scene.get(_LOCK_KEY, False):
                return {"RUNNING_MODAL"}

            s = self._state
            if s == "INIT":
                return self._state_init(context)
            elif s == "FIND_LOW":
                return self._state_find_low(context)
            elif s == "JUMP":
                return self._state_jump(context)
            elif s == "DETECT":
                return self._state_detect(context)
            elif s == "TRACK":
                return self._state_track(context)
            elif s == "CLEAN_SHORT":
                return self._state_clean_short(context)
            elif s == "CYCLE_FIND_MAX":
                return self._state_cycle_find_max(context)
            elif s == "CYCLE_SPIKE":
                return self._state_cycle_spike(context)
            elif s == "SOLVE":
                return self._state_solve(context)
            elif s == "EVAL":
                return self._state_eval(context)
            elif s == "CLEANUP":
                return self._state_cleanup(context)
            elif s == "FINALIZE":
                return self._finish(context, cancelled=False)

            _tco_log(f"Unknown state '{s}' → FINALIZE")
            return self._finish(context, cancelled=False)

        except Exception as ex:  # noqa: BLE001
            _tco_log(f"modal: unexpected exception: {ex!r}")
            return self._finish(context, cancelled=True)

    # ---------------- Finish ----------------

    def _finish(self, context, *, cancelled: bool):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        context.scene[_LOCK_KEY] = False
        msg = "CANCELLED" if cancelled else "FINISHED"
        print(f"[Coord] DONE ({msg})")
        return {"CANCELLED" if cancelled else "FINISHED"}


def register():
    register_scene_state()
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
    unregister_scene_state()


if __name__ == "__main__" and os.getenv("ADDON_RUN_TESTS", "0") == "1":
    print("[SelfTest] basic import OK")
