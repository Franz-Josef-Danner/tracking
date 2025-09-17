# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py â€“ Sequentieller Orchestrator (Solve vollständig entfernt)
- Phasen: FIND_LOW â†’ JUMP â†’ DETECT â†’ DISTANZE (hart getrennt, seriell)
- Camera-Solve, Eval/Refine, Post-Solve-Policies: entfernt.
"""

from __future__ import annotations

import gc
import time
import math
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

import bpy
from mathutils import Matrix, Vector

# --- Reentrancy-Lock + Bootstrap --------------------------------------------
# Single-run guard: prevents double-invoke while the modal is alive
_LOCK_KEY = "kc_coordinator_lock"


def _acquire_lock(context: bpy.types.Context) -> None:
    scn = getattr(context, "scene", None) or bpy.context.scene
    if not scn:
        return
    try:
        if bool(scn.get(_LOCK_KEY, False)):
            raise RuntimeError("Coordinator already running")
        scn[_LOCK_KEY] = True
    except RuntimeError:
        raise
    except Exception:
        # never crash on lock set
        pass


def _release_lock(context: bpy.types.Context) -> None:
    scn = getattr(context, "scene", None) or bpy.context.scene
    if not scn:
        return
    try:
        if _LOCK_KEY in scn.keys():
            del scn[_LOCK_KEY]
    except Exception:
        pass


def _bootstrap(context: bpy.types.Context) -> None:
    """Minimal, side-effect-free bootstrap: set lock and validate clip context."""

    _acquire_lock(context)

    # Ensure there is some MovieClip bound; assign first available as best effort.
    clip = getattr(context, "edit_movieclip", None) or getattr(
        getattr(context, "space_data", None), "clip", None
    )
    if clip:
        return

    try:
        movieclips = getattr(bpy.data, "movieclips", None)
        if movieclips:
            first = next(iter(movieclips), None)
            if first and getattr(context, "space_data", None):
                context.space_data.clip = first
    except Exception:
        # non-fatal
        pass

# --- optional import: error scorer ------------------------------------------
try:
    from ..Helper.count import error_value as _error_value  # type: ignore
except Exception:
    try:
        from .count import error_value as _error_value  # type: ignore
    except Exception:
        try:
            from Helper.count import error_value as _error_value  # type: ignore
        except Exception:
            _error_value = None  # type: ignore

class phase_lock:
    """Exklusiver Phasen-Lock; verhindert Nebenläufe in kritischen Abschnitten."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self) -> None:
        print(f"[PHASE] >>> {self.name} BEGIN")
        gc.disable()  # vermeidet GC-Spikes in Hot-Path

    def __exit__(self, exc_type, exc, tb) -> None:
        gc.enable()
        print(f"[PHASE] <<< {self.name} END")


@contextmanager
def undo_off():
    """Temporär Global-Undo aus (keine teuren Undo/Depsgraph-Sideeffects)."""

    prefs = bpy.context.preferences.edit
    old = prefs.use_global_undo
    prefs.use_global_undo = False
    try:
        yield
    finally:
        prefs.use_global_undo = old


# ---------------------------------------------------------------------------
# Öffentliche Hilfsfunktion: 3x Solve-Eval back-to-back, ohne Post-Processing
# ---------------------------------------------------------------------------
def solve_eval_back_to_back(
    *,
    clip,
    candidate_models: Iterable[Any],
    apply_model: Callable[[Any], None],
    do_solve: Callable[..., float],
    rank_callable: Optional[Callable[[float, Any], float]] = None,
    time_budget_sec: float = 10.0,
    max_trials: int = 3,
    quick: bool = True,
    solve_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """…(entfernt)…"""

    # >>> KOMPLETT ENTFERNT (Camera-Solve)
    raise RuntimeError("Camera solve code removed")


# ---------------------------------------------------------------------------
# Finaler Voll-Solve mit Intrinsics-Refine (fokal/principal/radial = True)
# ---------------------------------------------------------------------------
def solve_final_refine(
    *,
    context: bpy.types.Context,
    model: Any,
    apply_model: Callable[[Any], None],
    solve_full: Optional[Callable[..., float]] = None,
) -> float:
    """…(entfernt)…"""

    # >>> KOMPLETT ENTFERNT (Camera-Solve)
    raise RuntimeError("Camera solve code removed")


# ---------------------------------------------------------------------------
# Kombi-Wrapper: 3×-Eval + finaler Voll-Solve (alle refine_intrinsics = True)
# ---------------------------------------------------------------------------
def solve_eval_with_final_refine(
    *,
    clip,
    candidate_models: Iterable[Any],
    apply_model: Callable[[Any], None],
    do_solve_quick: Callable[..., float],
    solve_full: Optional[Callable[..., float]] = None,
    rank_callable: Optional[Callable[[float, Any], float]] = None,
    time_budget_sec: float = 10.0,
    max_trials: int = 3,
    quick: bool = True,
    solve_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """…(entfernt)…"""

    # >>> KOMPLETT ENTFERNT (Camera-Solve)
    raise RuntimeError("Camera solve code removed")


# ---------------------------------------------------------------------------
# Console logging
# ---------------------------------------------------------------------------
# To avoid cluttering the console with debug and status messages, all direct
# calls to ``print()`` in this module have been replaced by a no-op logger.
# The ``_log`` function can be used in place of ``print`` to completely
# suppress output. UI messages should continue to be emitted via ``self.report``.
def _log(*args, **kwargs):
    """No-op logger used to suppress console output."""
    return None
from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame, jump_to_frame
# Primitive importieren; Orchestrierung (Formel/Freeze) erfolgt hier.
from ..Helper.detect import run_detect_once as _primitive_detect_once
from ..Helper.distanze import run_distance_cleanup
from ..Helper.spike_filter_cycle import run_marker_spike_filter_cycle
from ..Helper.clean_short_segments import clean_short_segments
from ..Helper.clean_short_tracks import clean_short_tracks
from ..Helper.split_cleanup import recursive_split_cleanup
from ..Helper.find_max_marker_frame import run_find_max_marker_frame  # type: ignore
from ..Helper.reset_state import reset_for_new_cycle  # zentraler Reset (Bootstrap/Cycle)

# Versuche, die Auswertungsfunktion fÃ¼r die Markeranzahl zu importieren.
# Diese Funktion soll nach dem Distanz-Cleanup ausgefÃ¼hrt werden und
# verwendet interne Grenzwerte aus der count.py. Es werden keine
# zusÃ¤tzlichen Parameter Ã¼bergeben.
try:
    from ..Helper.count import evaluate_marker_count, run_count_tracks  # type: ignore
except Exception:
    try:
        from .count import evaluate_marker_count, run_count_tracks  # type: ignore
    except Exception:
        evaluate_marker_count = None  # type: ignore
        run_count_tracks = None  # type: ignore
from ..Helper.tracker_settings import apply_tracker_settings

# --- Anzahl/A-Werte/State-Handling ------------------------------------------
from ..Helper.tracking_state import (
    record_bidirectional_result,
    _get_state,          # intern genutzt, um count zu prÃ¼fen
    _ensure_frame_entry, # intern genutzt, um Frame-Eintrag zu holen
    reset_tracking_state,
    ABORT_AT,
)
# Fehlerwert-Funktion (Pfad ggf. anpassen)
try:
    from ..Helper.count import error_value  # type: ignore
    ERROR_VALUE_SRC = "..Helper.count.error_value"
    if _error_value is None:
        _error_value = error_value  # type: ignore[assignment]
except Exception:
    try:
        from .count import error_value  # type: ignore
        ERROR_VALUE_SRC = ".count.error_value"
        if _error_value is None:
            _error_value = error_value  # type: ignore[assignment]
    except Exception:
        def error_value(_track): return 0.0  # Fallback
        ERROR_VALUE_SRC = "FALLBACK_ZERO"
        if _error_value is None:
            _error_value = error_value  # type: ignore[assignment]


# ---- Solve-Logger: robust auflÃ¶sen, ohne auf Paketstruktur zu vertrauen ----
def _solve_log(context, value):
    """Laufzeit-sicherer Aufruf von __init__.kaiserlich_solve_log_add()."""
    try:
        import sys, importlib
        # 1) Root-Paket aus __package__/__name__ ableiten
        root_name = (__package__ or __name__).split(".", 1)[0]
        if not root_name:
            # Fallback: Vermutung "tracking"
            root_name = "tracking"
        mod = sys.modules.get(root_name)
        if mod and hasattr(mod, "kaiserlich_solve_log_add"):
            return getattr(mod, "kaiserlich_solve_log_add")(context, value)
        # 2) Hart nachladen, falls noch nicht importiert
        mod = importlib.import_module(root_name)
        fn = getattr(mod, "kaiserlich_solve_log_add", None)
        if callable(fn):
            return fn(context, value)
    except Exception:
        pass
    # Silent: kein Crash, wenn das Log-Addon noch nicht geladen ist
    return
# Optional: den Bidirectionalâ€‘Track Operator importieren. Wenn der Import
# fehlschlÃ¤gt, bleibt die Variable auf None und es erfolgt kein Aufruf.
try:
    from ..Helper.bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
except Exception:
    try:
        from .bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
    except Exception:
        CLIP_OT_bidirectional_track = None  # type: ignore

# -----------------------------------------------------------------------------
# Optionally import the multi-pass helper. This helper performs additional
# feature detection passes with varied pattern sizes. It will be invoked when
# the marker count evaluation reports that the number of markers lies within
# the acceptable range ("ENOUGH").
try:
    # Prefer package-style import when the Helper package is available
    from ..Helper.multi import run_multi_pass  # type: ignore
except Exception:
    try:
        # Fallback to local import when running as a standalone module
        from .multi import run_multi_pass  # type: ignore
    except Exception:
        # If import fails entirely, leave run_multi_pass as None
        run_multi_pass = None  # type: ignore
from ..Helper.marker_helper_main import marker_helper_main
# Import the detect threshold key so we can reference the last used value
try:
    # Local import when running inside the package structure
    from ..Helper.detect import DETECT_LAST_THRESHOLD_KEY  # type: ignore
except Exception:
    try:
        # Fallback when module layout differs
        from .detect import DETECT_LAST_THRESHOLD_KEY  # type: ignore
    except Exception:
        # Default value if import fails
        DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # type: ignore

__all__ = ("CLIP_OT_tracking_coordinator",)

# --- Phasen-Konstanten -----------------------------------------------------
PH_FIND_LOW = "FIND_LOW"
PH_JUMP = "JUMP"
PH_DETECT = "DETECT"
PH_DISTANZE = "DISTANZE"
PH_SPIKE_CYCLE = "SPIKE_CYCLE"
PH_BIDI = "BIDI"

# --- Solve-bezogene Policies/Hooks wurden vollständig entfernt. ---


def post_solve_quality_check(context):
    """ Hook nach einem erfolgreichen Solve: prüft Solve-Log, löscht ggf. Marker,
        und signalisiert dem Orchestrator, ob ein Reset → FindLow nötig ist.
    """

    # >>> KOMPLETT ENTFERNT (Camera-Solve)
    return False

def _route_to_find_low(context):
    """Springt sicher zurück zur Find-Low-Phase und setzt den Playhead."""

    try:
        _set_scene_frame_to_nearest_recon_or_start(context)
    except Exception:
        pass
    try:
        out = run_find_low_marker_frame(context)
        if isinstance(out, dict) and str(out.get("status")) == "FOUND":
            frame = int(out.get("frame", 0))
            try:
                jump_to_frame(context, frame=frame, ui_override=True, spread_rings=2)
            except Exception as _jump_exc:
                print(f"[FindLow] jump_to_frame failed: {_jump_exc!r}")
            return "FIND_LOW"
    except Exception as _exc:
        print(f"[FindLow] routing failed: {_exc!r}")
    return "CYCLE_START"


# ---------------------------------------------------------------------------
# Globaler Guard-State (persistiert über Resets)
_INFCOST_STATE: dict[str, dict[str, float | int]] = {}
_SOLVE_ERR_DEFAULT_THR = 20.0


# --- Clip/Frame Utilities ----------------------------------------------------
def _ensure_scene_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Sichert scene.active_clip ab und liefert ihn zurück."""

    # unverändert …
    try:
        scn = getattr(context, "scene", None) or bpy.context.scene
        clip = getattr(scn, "active_clip", None)
        if clip:
            return clip
        sd = getattr(getattr(context, "space_data", None), "clip", None)
        if sd:
            scn.active_clip = sd
            return sd
        if getattr(bpy.data, "movieclips", None):
            scn.active_clip = bpy.data.movieclips[0]
            return scn.active_clip
    except Exception:
        pass
    return None


def _nearest_recon_frame(clip: bpy.types.MovieClip, ref_frame: int) -> Optional[int]:
    """Ermittelt den existierenden Recon-Frame, der ref_frame am nächsten liegt."""

    try:
        frames: list[int] = []
        rec = getattr(clip.tracking, "reconstruction", None)
        cams = list(getattr(rec, "cameras", [])) if rec else []
        for c in cams:
            try:
                frames.append(int(getattr(c, "frame", None)))
            except Exception:
                pass
        for obj in getattr(clip.tracking, "objects", []):
            rec_o = getattr(obj, "reconstruction", None)
            for c in (list(getattr(rec_o, "cameras", [])) if rec_o else []):
                try:
                    frames.append(int(getattr(c, "frame", None)))
                except Exception:
                    pass
        if not frames:
            return None
        # nearest by absolute distance; tie -> lower frame
        return sorted(frames, key=lambda f: (abs(f - ref_frame), f))[0]
    except Exception:
        return None


def _has_camera_for_frame(clip: bpy.types.MovieClip, frame: int) -> bool:
    try:
        robj = clip.tracking.objects.active.reconstruction  # type: ignore[union-attr]
        cams = getattr(robj, "cameras", [])
        return any(int(getattr(c, "frame", -10**9)) == int(frame) for c in cams)
    except Exception:
        return False


def _set_scene_frame_to_nearest_recon(context: bpy.types.Context) -> None:
    """Erzwingt einen gültigen Recon-Frame (persistiert, kein Zurücksetzen)."""

    scn = getattr(context, "scene", None) or bpy.context.scene
    clip = _ensure_scene_active_clip(context)
    if not scn or not clip:
        return
    cur = int(scn.frame_current)
    tgt = _nearest_recon_frame(clip, cur)
    if tgt is not None and tgt != cur:
        scn.frame_set(int(tgt))


# --- UI/Context Utilities ----------------------------------------------------
def _find_clip_editor_override(context: bpy.types.Context, clip: bpy.types.MovieClip) -> Optional[dict]:
    """Liefert einen belastbaren Context-Override für CLIP_EDITOR + bindet den Clip."""

    try:
        for win in bpy.context.window_manager.windows:
            scr = win.screen
            for area in scr.areas:
                if area.type != 'CLIP_EDITOR':
                    continue
                for region in area.regions:
                    if region.type != 'WINDOW':
                        continue
                    space = area.spaces.active
                    if getattr(space, "type", "") != 'CLIP_EDITOR':
                        continue
                    # Clip binden
                    try:
                        space.clip = clip
                    except Exception:
                        pass
                    return {
                        "window": win,
                        "screen": scr,
                        "area": area,
                        "region": region,
                        "space_data": space,
                        "scene": getattr(context, "scene", None) or bpy.context.scene,
                    }
    except Exception:
        pass
    return None


def _select_only_track(clip: bpy.types.MovieClip, container, trk, *, is_top_level: bool) -> None:
    """Selektiert ausschließlich den angegebenen Track (Top-Level + Objektpfad werden bereinigt)."""

    # alles deselektieren
    try:
        for t in getattr(clip.tracking, "tracks", []):
            t.select = False
    except Exception:
        pass
    try:
        for obj in getattr(clip.tracking, "objects", []):
            for t in getattr(obj, "tracks", []):
                t.select = False
    except Exception:
        pass
    # aktives Objekt setzen (für Objekt-Tracks) und gewünschten Track selektieren
    try:
        if not is_top_level and hasattr(clip.tracking, "objects"):
            # container ist hier MovieTrackingObject
            clip.tracking.objects.active = container
    except Exception:
        pass
    try:
        trk.select = True
        # optional active setzen (hilft manchen Ops)
        try:
            getattr(container, "active_track")
            container.active_track = trk
        except Exception:
            pass
    except Exception:
        pass


# --- Recon-Inventory ---------------------------------------------------------
def _has_any_recon_cameras(clip: bpy.types.MovieClip) -> bool:
    """True, wenn mindestens eine Reconstruction-Kamera (egal in welchem Objekt) existiert."""

    try:
        cams = []
        try:
            cams += list(getattr(getattr(clip.tracking, "reconstruction", None), "cameras", []))
        except Exception:
            pass
        for obj in getattr(clip.tracking, "objects", []):
            try:
                cams += list(getattr(getattr(obj, "reconstruction", None), "cameras", []))
            except Exception:
                pass
        return len(cams) > 0
    except Exception:
        return False


def _max_recon_camera_frame(clip: bpy.types.MovieClip) -> Optional[int]:
    """Ermittelt den höchsten Frame einer vorhandenen Recon-Kamera."""

    try:
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            return None
        frames: list[int] = []
        recon_main = getattr(tracking, "reconstruction", None)
        if recon_main:
            for cam in getattr(recon_main, "cameras", []) or []:
                frame = getattr(cam, "frame", None)
                if frame is None:
                    continue
                try:
                    frames.append(int(frame))
                except Exception:
                    continue
        for obj in getattr(tracking, "objects", []):
            recon_obj = getattr(obj, "reconstruction", None)
            if recon_obj is None:
                continue
            for cam in getattr(recon_obj, "cameras", []) or []:
                frame = getattr(cam, "frame", None)
                if frame is None:
                    continue
                try:
                    frames.append(int(frame))
                except Exception:
                    continue
        if not frames:
            return None
        return max(frames)
    except Exception:
        return None


def _set_scene_frame_to_nearest_recon_or_start(context: bpy.types.Context) -> None:
    scn = getattr(context, "scene", None) or bpy.context.scene
    clip = _ensure_scene_active_clip(context)
    if not scn or not clip:
        return
    # wenn Recon existiert → nearest; sonst Clip-Start
    if _has_any_recon_cameras(clip):
        nr = _nearest_recon_frame(clip, int(scn.frame_current))
        if nr is not None:
            try:
                scn.frame_set(int(nr))
            except Exception:
                pass
            return
    try:
        scn.frame_set(int(getattr(clip, "frame_start", scn.frame_start)))
    except Exception:
        pass


def _clamp_scene_frame_to_recon(context: bpy.types.Context) -> None:
    """Falls der aktuelle Scene-Frame keine Recon-Kamera hat, auf den nächsten gültigen Frame setzen."""

    scn = getattr(context, "scene", None) or bpy.context.scene
    clip = _ensure_scene_active_clip(context)
    if not scn or not clip:
        return
    cur = int(scn.frame_current)
    if _has_camera_for_frame(clip, cur):
        return
    tgt = _nearest_recon_frame(clip, cur)
    if tgt is not None:
        scn.frame_set(int(tgt))


@contextmanager
def _with_valid_camera_frame(context: bpy.types.Context):  # temporärer Guard
    """Temporär auf einen Recon-Frame springen, um 'No camera for frame X' zu vermeiden."""

    scn = getattr(context, "scene", None) or bpy.context.scene
    clip = _ensure_scene_active_clip(context)
    if scn is None or clip is None:
        yield
        return

    try:
        frame_start, frame_end = _clip_frame_range(clip)
    except Exception:
        frame_start = frame_end = int(getattr(scn, "frame_current", 0))
    frame_start = int(frame_start)
    frame_end = int(frame_end)
    if frame_end < frame_start:
        frame_end = frame_start

    max_cam = _max_recon_camera_frame(clip)
    check_end = frame_end
    if max_cam is not None:
        try:
            check_end = min(frame_end, int(max_cam))
        except Exception:
            check_end = frame_end
    if check_end < frame_start:
        check_end = frame_start

    prev = int(getattr(scn, "frame_current", check_end))
    restore_frame = prev if prev <= check_end else check_end
    if prev > check_end:
        try:
            scn.frame_set(int(check_end))
        except Exception:
            pass

    try:
        current = int(getattr(scn, "frame_current", restore_frame))
        target = _nearest_recon_frame(clip, current)
        if target is not None and target != current:
            scn.frame_set(int(target))
        yield
    finally:
        try:
            if int(getattr(scn, "frame_current", restore_frame)) != int(restore_frame):
                scn.frame_set(int(restore_frame))
        except Exception:
            pass


# ---------- Recon Frame Helpers ----------
def _bundle_co(trk) -> Optional[Vector]:
    try:
        if getattr(trk, "has_bundle", False):
            b = getattr(trk, "bundle", None)
            if b is None:
                return None
            # b kann Vector oder Objekt mit .co sein
            if hasattr(b, "co"):
                return Vector(b.co)
            return Vector(b)
    except Exception:
        pass
    return None


def _iter_recon_cam_mats(clip) -> Iterable[Tuple[int, Matrix]]:
    """Liefert (frame, cam_matrix) aus allen Recon-Containern; robust gegen API-Varianz."""

    try:
        rec = getattr(clip.tracking, "reconstruction", None)
        for c in (list(getattr(rec, "cameras", [])) if rec else []):
            f = int(getattr(c, "frame", -10**9))
            m = getattr(c, "matrix", None)
            if m is not None:
                yield (f, Matrix(m))
    except Exception:
        pass
    for obj in getattr(clip.tracking, "objects", []):
        try:
            rec_o = getattr(obj, "reconstruction", None)
            for c in (list(getattr(rec_o, "cameras", [])) if rec_o else []):
                f = int(getattr(c, "frame", -10**9))
                m = getattr(c, "matrix", None)
                if m is not None:
                    yield (f, Matrix(m))
        except Exception:
            continue


def _purge_negative_depth_bundles(
    context: bpy.types.Context, max_deletes: int = 25
) -> Tuple[int, int]:
    """Entfernt Marker/Tracks, deren Bundle relativ zu ≥2 Kameras negative Tiefe hat.
       Rückgabe: (markers_deleted, tracks_removed)."""

    clip = _ensure_scene_active_clip(context)
    if not clip or not _has_any_recon_cameras(clip):
        return (0, 0)
    cam_mats = list(_iter_recon_cam_mats(clip))
    if len(cam_mats) < 2:
        return (0, 0)
    del_mk, del_tr = 0, 0
    deletes_left = max(1, int(max_deletes))
    for container, trk, is_top in _iter_all_tracks(clip):
        if deletes_left <= 0:
            break
        try:
            co = _bundle_co(trk)
            if co is None:
                continue
            neg_hits = 0
            co_h = Vector((co.x, co.y, co.z, 1.0))
            for _, M in cam_mats[:8]:  # Limit aus Performancegründen
                try:
                    cam_space = M.inverted_safe() @ co_h
                    if float(cam_space.z) <= 0.0:
                        neg_hits += 1
                        if neg_hits >= 2:
                            break
                except Exception:
                    continue
            if neg_hits >= 2:
                # Primär Marker löschen; wenn praktisch leer → Track löschen
                frames: list[int] = []
                for m in list(getattr(trk, "markers", [])):
                    try:
                        frames.append(int(getattr(m, "frame", 0)))
                    except Exception:
                        pass
                for fr in sorted(set(frames)):
                    try:
                        trk.markers.delete_frame(fr)
                        del_mk += 1
                    except Exception:
                        pass
                _select_only_track(clip, container, trk, is_top_level=is_top)
                ov = _find_clip_editor_override(context, clip)
                deleted = False
                if ov:
                    with bpy.context.temp_override(**ov):
                        if bpy.ops.clip.delete_track(confirm=False) == {'FINISHED'}:
                            del_tr += 1
                            deleted = True
                if not deleted and _delete_track_hard(
                    container, trk, is_top_level=is_top
                ):
                    del_tr += 1
                deletes_left -= 1
        except Exception:
            continue
    if del_mk or del_tr:
        print(f"[BehindCam] purged markers={del_mk} tracks={del_tr}")
    return (del_mk, del_tr)


# --- Safe Reduce Wrapper -----------------------------------------------------
def _iter_all_tracks(clip: bpy.types.MovieClip):
    """Liefert (container, trk, is_top_level). container ist entweder clip.tracking (Top-Level)
    oder ein MovieTrackingObject (Objekt-Tracks)."""

    try:
        for trk in getattr(clip.tracking, "tracks", []):
            yield (clip.tracking, trk, True)
    except Exception:
        pass
    try:
        for obj in getattr(clip.tracking, "objects", []):
            for trk in getattr(obj, "tracks", []):
                yield (obj, trk, False)
    except Exception:
        pass


def _delete_track_hard(container, trk, *, is_top_level: bool) -> bool:
    """Entfernt Track robust:
       1) direkter remove()
       2) Marker vollständig löschen → remove() erneut.
       Liefert True bei Erfolg; loggt präzise Fehlerursachen."""

    # 1) direkter Remove
    try:
        getattr(container, "tracks").remove(trk)
        return True
    except Exception as ex:
        print(
            f"[ReduceDBG][hard] remove() failed 1st: name={getattr(trk,'name','?')} top={is_top_level} ex={ex!r}"
        )
    # 2) alle Marker löschen
    try:
        mks = list(getattr(trk, "markers", []))
        frames = [int(getattr(m, "frame", 0)) for m in mks]
        for fr in sorted(set(frames)):
            try:
                trk.markers.delete_frame(fr)
            except Exception as ex2:
                print(f"[ReduceDBG][hard] delete_frame({fr}) failed: {ex2!r}")
        # erneut versuchen zu entfernen
        try:
            getattr(container, "tracks").remove(trk)
            return True
        except Exception as ex3:
            print(
                f"[ReduceDBG][hard] remove() failed 2nd: name={getattr(trk,'name','?')} "
                f"markers={len(getattr(trk,'markers',[]))} ex={ex3!r}"
            )
    except Exception as ex:
        print(f"[ReduceDBG][hard] marker purge failed: name={getattr(trk,'name','?')} ex={ex!r}")
    return False


def _track_error_estimate(trk) -> float:
    """Bestmögliche Fehler-Schätzung je Track."""

    if _error_value is not None:
        try:
            return float(_error_value(trk))
        except Exception:
            pass
    for attr in ("average_error", "avg_error", "error"):
        try:
            v = getattr(trk, attr)
            if isinstance(v, (int, float)):
                return float(v)
        except Exception:
            pass
    try:
        return -float(len(getattr(trk, "markers", [])))
    except Exception:
        return 0.0


def _emergency_reduce_by_error(context: bpy.types.Context, *, max_to_delete: int = 5) -> int:
    """Notfall-Reducer: löscht bis zu N Tracks mit höchstem error_value()."""

    clip = _ensure_scene_active_clip(context)
    if not clip:
        return 0
    deleted = 0
    try:
        rows: list[tuple[float, Any, Any, bool]] = []  # (err, container, trk, is_top_level)
        for container, trk, is_top in _iter_all_tracks(clip):
            err = _track_error_estimate(trk)
            rows.append((float(err), container, trk, is_top))
        if not rows:
            print("[ReduceDBG][fallback] keine Tracks gefunden (Top-Level + Obj).")
            return 0
        rows.sort(key=lambda r: r[0], reverse=True)
        budget = max(0, int(max_to_delete))
        for err, container, trk, is_top in rows[:budget]:
            ok = False
            # (A) interner Remove/Hard-Purge (für kompatible Builds)
            ok = _delete_track_hard(container, trk, is_top_level=is_top)
            if not ok:
                # (B) Operator-Weg: selektieren + bpy.ops.clip.delete_track(confirm=False)
                try:
                    _select_only_track(clip, container, trk, is_top_level=is_top)
                    ov = _find_clip_editor_override(context, clip)
                    if ov:
                        with bpy.context.temp_override(**ov):
                            r = bpy.ops.clip.delete_track(confirm=False)
                            ok = (r == {"FINISHED"})
                            if not ok:
                                print(
                                    f"[ReduceDBG][ops] delete_track returned={r} name={getattr(trk,'name','?')}"
                                )
                    else:
                        print("[ReduceDBG][ops] no CLIP_EDITOR override available.")
                except Exception as ex_ops:
                    print(f"[ReduceDBG][ops] delete_track failed: {ex_ops!r}")
            if ok:
                deleted += 1
            else:
                # (C) Letzte Eskalation: muten (sichtbar loggen)
                try:
                    setattr(trk, "mute", True)
                except Exception:
                    pass
                print(
                    f"[ReduceDBG][hard] could not remove → muted: name={getattr(trk,'name','?')} err={err:.3f}"
                )
        print(f"[ReduceDBG][fallback] candidates={len(rows)} removed={deleted}/{budget}")
    except Exception as ex:
        print(f"[ReduceDBG][fallback] failed: {ex!r}")
    return deleted


# --- Solve-bezogene Cleanup-Helfer entfernt. ---

def _resolve_clip(context: bpy.types.Context):
    """Robuster Clip-Resolver (Edit-Clip, Space-Clip, erster Clip)."""
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip

def _reset_margin_to_tracker_default(context: bpy.types.Context) -> None:
    """No-Op beibehalten (API-Stabilität), aber faktisch ignorieren:
    Die *operativen* Werte kommen aus marker_helper_main (Scene-Keys)."""
    try:
        clip = _resolve_clip(context)
        tr = getattr(clip, "tracking", None) if clip else None
        settings = getattr(tr, "settings", None) if tr else None
        if settings and hasattr(settings, "default_margin"):
            # Setzen wir auf den Scene-Wert, wenn vorhanden – ohne Berechnung.
            scn = context.scene
            m = int(scn.get("margin_base") or 0)
            if m > 0:
                settings.default_margin = int(m)
                _log(f"[Coordinator] default_margin ← scene.margin_base={m}")
    except Exception as exc:
        _log(f"[Coordinator] WARN: margin reset fallback: {exc}")

def _marker_count_by_selected_track(context: bpy.types.Context) -> dict[str, int]:
    """Anzahl Marker je *ausgewÃ¤hltem* Track (Name -> Count)."""
    clip = _resolve_clip(context)
    out: dict[str, int] = {}
    if not clip:
        return out
    trk = getattr(clip, "tracking", None)
    if not trk:
        return out
    for t in trk.tracks:
        try:
            if getattr(t, "select", False):
                out[t.name] = len(t.markers)
        except Exception:
            pass
    return out

def _delta_counts(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    """Delta = after - before (clamp â‰¥ 0)."""
    names = set(before) | set(after)
    return {n: max(0, int(after.get(n, 0)) - int(before.get(n, 0))) for n in names}

def _snapshot_track_ptrs(context: bpy.types.Context) -> list[int]:
    """
    Snapshot der aktuellen Track-Pointer.
    WICHTIG: Diese Werte NICHT in Scene/IDProperties persistieren (32-bit Limit)!
    Nur ephemer im Python-Kontext verwenden.
    """
    clip = _resolve_clip(context)
    if not clip:
        return []
    try:
        return [int(t.as_pointer()) for t in clip.tracking.tracks]
    except Exception:
        return []


def _clip_frame_range(clip):
    fs = int(getattr(clip, "frame_start", 1))
    fd = int(getattr(clip, "frame_duration", 0))
    if fd > 0:
        return fs, fs + fd - 1
    frames = []
    tr = clip.tracking
    tracks = tr.objects.active.tracks if tr.objects.active else tr.tracks
    for t in tracks:
        frames.extend([mk.frame for mk in t.markers])
    if frames:
        return min(frames), max(frames)
    scn = bpy.context.scene
    return int(getattr(scn, "frame_start", 1)), int(getattr(scn, "frame_end", 1))

def _initialize_helpers(context: bpy.types.Context) -> None:
    """Minimaler Reset + sinnvolle Defaults; Helper initialisieren."""
    scn = context.scene
    # Tracker-Settings
    try:
        scn["tco_last_tracker_settings"] = dict(apply_tracker_settings(context, scene=scn, log=True))
    except Exception as exc:
        scn["tco_last_tracker_settings"] = {"status": "FAILED", "reason": str(exc)}
    # Marker-Helper
    try:
        ok, count, info = marker_helper_main(context)
        scn["tco_last_marker_helper"] = {
            "ok": bool(ok),
            "count": int(count),
            "info": dict(info) if hasattr(info, "items") else info,
        }
    except Exception as exc:
        scn["tco_last_marker_helper"] = {"status": "FAILED", "reason": str(exc)}


# --- Operator: wird vom UI-Button aufgerufen -------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking Coordinator (Modal, strikt sequenziell)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator (Modal)"
    # Hinweis: Blender kennt nur GRAB_CURSOR / GRAB_CURSOR_X / GRAB_CURSOR_Y.
    # GRAB_CURSOR_XY existiert nicht â†’ Validation-Error beim Register.
    # ModalitÃ¤t kommt Ã¼ber modal(); Cursor-Grabbing ist nicht nÃ¶tig.
    bl_options = {"REGISTER", "UNDO"}

    # â€” Laufzeit-State (nur Operator, nicht Szene) â€”
    _timer: object | None = None
    phase: str = PH_FIND_LOW
    target_frame: int | None = None
    repeat_map: dict[int, int] = {}
    pre_ptrs: set[int] | None = None
    repeat_count_for_target: int | None = None
    # Aktueller Detection-Threshold; wird nach jedem Detect-Aufruf aktualisiert.
    detection_threshold: float | None = None
    spike_threshold: float | None = None  # aktueller Spike-Filter-Schwellenwert (temporÃ¤r)
    # Telemetrie (optional)
    last_detect_new_count: int | None = None
    last_detect_min_distance: int | None = None
    last_detect_margin: int | None = None

    def _run_detect_with_policy(
        self,
        context: bpy.types.Context,
        *,
        threshold: float | None = None,
        # optional Guard: erlaubt explizite Vorgabe für min_distance
        min_distance: int | None = None,
        placement: str = "FRAME",
        select: bool | None = None,
        **kwargs,
    ) -> dict:
        scn = context.scene
        # 1) Operative Baselines ausschließlich aus marker_helper_main (Scene-Keys)
        fixed_margin = int(scn.get("margin_base") or 0)
        if fixed_margin <= 0:
            # Harter Fallback, falls MarkerHelper noch nicht gelaufen ist
            clip = _resolve_clip(context)
            w = int(getattr(clip, "size", (800, 800))[0]) if clip else 800
            patt = max(8, int(w / 100))
            fixed_margin = patt * 2

        # 2) Threshold: harter Fixwert (Anforderung)
        #    Kein Fallback, keine Last-Detection – immer exakt 0.0001.
        curr_thr = 0.0001  # FIXED

        # *** min_distance: exakt nach Vorgabe ***
        # Priorität NUR:
        #   1) expliziter Funktionsparameter
        #   2) zuletzt gestufter Wert: scene["tco_detect_min_distance"]
        #   3) Startwert ausschließlich aus marker_helper_main: scene["min_distance_base"]
        if min_distance is not None:
            curr_md = float(min_distance)
            md_source = "param"
        else:
            tco_md = scn.get("tco_detect_min_distance")
            if isinstance(tco_md, (int, float)) and float(tco_md) > 0.0:
                curr_md = float(tco_md)
                md_source = "tco"
            else:
                base_md = scn.get("min_distance_base")
                # Erwartung: marker_helper_main hat base gesetzt.
                curr_md = float(base_md if base_md is not None else 0.0)
                md_source = "base"

        last_nc = int(scn.get("tco_last_detect_new_count") or -1)
        target = 100
        for k in ("tco_detect_target", "detect_target", "marker_target", "target_new_markers"):
            v = scn.get(k)
            if isinstance(v, (int, float)) and int(v) > 0:
                target = int(v)
                break

        # 3) Detect ausführen (select passthrough, KEINE Berechnung von margin/md hier)
        before = _marker_count_by_selected_track(context)
        res = _primitive_detect_once(
            context,
            threshold=curr_thr,
            margin=fixed_margin,
            # Blender erwartet int-Pixel; die Stufung selbst bleibt float-genau.
            min_distance=int(round(curr_md)) if curr_md is not None else 0,
            placement=placement,
            select=select,
            **kwargs,
        )
        after = _marker_count_by_selected_track(context)
        new_count = sum(max(0, int(v)) for v in _delta_counts(before, after).values())

        # 4) Formeln anwenden – AB JETZT basiert beides auf dem Count aus count.py.
        #    Dieser Wert wird nach DISTANZE via evaluate_marker_count() gesetzt.
        #    Fallback auf new_count nur, falls noch kein Count vorliegt (erstes Pass).
        gm_for_formulas = context.scene.get("tco_count_for_formulas")
        try:
            gm_for_formulas = float(gm_for_formulas) if gm_for_formulas is not None else float(new_count)
        except Exception:
            gm_for_formulas = float(new_count)

        # Threshold NICHT stufen – fixer Wert je Pass
        next_thr = curr_thr  # = 0.0001

        # min_distance JEDEM PASS stufen – Gate entfernt
        za = float(target)
        gm = float(gm_for_formulas)
        f_md = 1.0 - (
            (za - gm) / (za * (20.0 / max(1, min(7, abs(za - gm) / 10))))
        )
        next_md = float(curr_md) * f_md

        # 5) Persistieren
        scn["tco_last_detect_new_count"] = int(new_count)
        scn["tco_detect_thr"] = float(next_thr)
        scn["tco_detect_min_distance"] = float(next_md)
        scn["tco_detect_margin"] = int(fixed_margin)
        # Sofortige Sichtbarkeit für DISTANZE (liest kc_*):
        try:
            scn["kc_detect_min_distance_px"] = int(round(next_md))
        except Exception:
            pass
        # WICHTIG: den Count, der für die Formeln verwendet wurde, ebenfalls persistieren
        scn["tco_last_count_for_formulas"] = int(gm_for_formulas)
        _log(
            f"[DETECT] new={new_count} target={target} "
            f"thr->{next_thr:.7f} (fixed) "
            f"md_curr->{curr_md:.6f} md_next->{next_md:.6f} "
            f"src={md_source} (gate=OFF)"
        )
        return res

    # Flag, ob der Bidirectional-Track bereits gestartet wurde. Diese
    # Instanzvariable dient dazu, den Start der Bidirectionalâ€‘Track-Phase
    # nur einmal auszulÃ¶sen und anschlieÃŸend auf den Abschluss zu warten.
    bidi_started: bool = False
    bidi_before_counts: dict[str, int] | None = None  # Snapshot vor BIDI
    # TemporÃ¤rer Schwellenwert fÃ¼r den Spike-Cycle (startet bei 100, *0.9)
    # NEU: Wurde bereits die volle Intrinsics-Variante (focal+principal+radial) versucht?
    def execute(self, context: bpy.types.Context):
        # Bootstrap/Reset
        try:
            _bootstrap(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Bootstrap failed: {exc}")
            try:
                _release_lock(context)
            except Exception:
                pass
            return {'CANCELLED'}

        try:
            _initialize_helpers(context)
        except Exception as exc:
            try:
                _release_lock(context)
            except Exception:
                pass
            self.report({'ERROR'}, f"Helper bootstrap failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator: Bootstrap OK")

        # Bootstrap: harter Neustart + Solve-Error-Log leeren
        try:
            reset_for_new_cycle(context, clear_solve_log=True)
        except Exception as exc:
            try:
                _release_lock(context)
            except Exception:
                pass
            self.report({'ERROR'}, f"Reset failed: {exc}")
            return {'CANCELLED'}
        # ZusÃ¤tzlich: State von tracking_state.py zurÃ¼cksetzen
        try:
            reset_tracking_state(context)
            self.report({'INFO'}, "Tracking-State zurÃ¼ckgesetzt")
        except Exception as exc:
            self.report({'WARNING'}, f"Tracking-State Reset fehlgeschlagen: {exc}")

        # Modal starten
        self.phase = PH_FIND_LOW
        self.target_frame = None
        self.repeat_map = {}
        self.pre_ptrs = None
        # Threshold-ZurÃ¼cksetzen: beim ersten Detect-Aufruf wird der Standardwert verwendet
        self.detection_threshold = None
        # Bidirectionalâ€‘Track ist noch nicht gestartet
        self.spike_threshold = None  # Spike-Schwellenwert zurÃ¼cksetzen
        self.bidi_before_counts = None
        self.repeat_count_for_target = None
        # Herkunft der Fehlerfunktion einmalig ausgeben (sichtbar im UI)
        try:
            self.report({'INFO'}, f"error_value source: {ERROR_VALUE_SRC}")
            if ERROR_VALUE_SRC == 'FALLBACK_ZERO':
                self.report({'WARNING'}, 'Fallback error_value aktiv (immer 0.0) â€“ bitte Helper/count.py installieren.')
        except Exception:
            pass

        
        wm = context.window_manager
        # --- Robust: valides Window sichern ---
        win = getattr(context, "window", None)
        if not win:
            try:
                # aus dem Clip-Override ziehen
                win = _ensure_clip_context(context).get("window", None)
            except Exception:
                win = None
        if not win:
            # Fallback: globaler Context
            win = getattr(bpy.context, "window", None)
        try:
            # Wenn win None ist, Timer OHNE window anlegen (Blender erlaubt das)
            self._timer = wm.event_timer_add(0.10, window=win) if win else wm.event_timer_add(0.10)
            self.report({'INFO'}, f"Timer status=OK (window={'set' if win else 'none'})")
        except Exception as exc:
            self.report({'WARNING'}, f"Timer setup failed ({exc}); retry without window")
            try:
                self._timer = wm.event_timer_add(0.10)
            except Exception as exc2:
                self.report({'ERROR'}, f"Timer hard-failed: {exc2}")
                try:
                    _release_lock(context)
                except Exception:
                    pass
                return {'CANCELLED'}
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context, *, info: str | None = None, cancelled: bool = False):
        # Timer sauber entfernen
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None
        try:
            self._restore_holdouts(context)
        except Exception:
            pass
        # Release reentrancy lock
        try:
            _release_lock(context)
        except Exception:
            pass
        if info:
            self.report({'INFO'} if not cancelled else {'WARNING'}, info)
        return {'CANCELLED' if cancelled else 'FINISHED'}

    def modal(self, context: bpy.types.Context, event):
        # --- ESC / Abbruch prÃ¼fen ---
        if event.type in {'ESC'} and event.value == 'PRESS':
            return self._finish(context, info="ESC gedrÃ¼ckt â€“ Prozess abgebrochen.", cancelled=True)

        # nur Timer-Events verarbeiten
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        # Optionales Debugging: erste 3 Ticks loggen
        try:
            count = int(getattr(self, "_dbg_tick_count", 0)) + 1
            if count <= 3:
                self.report({'INFO'}, f"TIMER tick #{count}, phase={self.phase}")
            self._dbg_tick_count = count
        except Exception:
            pass

        # PHASE 1: FIND_LOW
        if self.phase == PH_FIND_LOW:
            res = run_find_low_marker_frame(context)
            st = res.get("status")
            if st == "FAILED":
                return self._finish(context, info=f"FIND_LOW FAILED â†’ {res.get('reason')}", cancelled=True)
            if st == "NONE":
                # Kein Low-Marker-Frame gefunden: Starte Spike-Zyklus
                self.phase = PH_SPIKE_CYCLE
                self.spike_threshold = 100.0
                return {'RUNNING_MODAL'}
            self.target_frame = int(res.get("frame"))
            self.report({'INFO'}, f"Low-Marker-Frame: {self.target_frame}")
            self.phase = PH_JUMP
            return {'RUNNING_MODAL'}

        # PHASE 2: JUMP
        if self.phase == PH_JUMP:
            if self.target_frame is None:
                return self._finish(context, info="JUMP: Kein Ziel-Frame gesetzt.", cancelled=True)
            rj = run_jump_to_frame(context, frame=self.target_frame, repeat_map=self.repeat_map)
            if rj.get("status") != "OK":
                return self._finish(context, info=f"JUMP FAILED â†’ {rj}", cancelled=True)
            self.report({'INFO'}, f"Playhead gesetzt: f{rj.get('frame')} (repeat={rj.get('repeat_count')})")

            # NEU: Anzahl/Motion-Model aus SSOT lesen und ggf. bei 10 abbrechen
            try:
                _state = _get_state(context)
                _entry, _ = _ensure_frame_entry(_state, int(self.target_frame))
                _count = int(_entry.get("count", 1))
                self.repeat_count_for_target = _count
                if _count >= ABORT_AT:
                    return self._finish(
                        context,
                        info=f"Abbruch: Frame {self.target_frame} hat {ABORT_AT-1} DurchlÃ¤ufe erreicht.",
                        cancelled=True
                    )
            except Exception as _exc:
                self.report({'WARNING'}, f"Repeat count read warn: {str(_exc)}")

            # --- Snapshot VOR Detect ziehen (Fix für RC#2) ---
            self.pre_ptrs = set(_snapshot_track_ptrs(context))
            try:
                clip = _resolve_clip(context)
                cur_frame = self.target_frame
                print(
                    f"[COORD] Pre Detect: tracks={len(getattr(clip.tracking,'tracks',[]))} "
                    f"snapshot_size={len(self.pre_ptrs)} frame={cur_frame}"
                )
            except Exception:
                pass
            self.phase = PH_DETECT
            return {'RUNNING_MODAL'}

        # PHASE 3: DETECT
        if self.phase == PH_DETECT:
            try:
                scn = context.scene
                _lt = float(scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
                if _lt <= 1e-6:
                    scn[DETECT_LAST_THRESHOLD_KEY] = 0.75
            except Exception:
                pass

            rd = self._run_detect_with_policy(
                context,
                start_frame=self.target_frame,
                threshold=self.detection_threshold,
            )
            if rd.get("status") != "READY":
                return self._finish(context, info=f"DETECT FAILED → {rd}", cancelled=True)
            new_cnt = int(rd.get("new_tracks", 0))
            try:
                scn = context.scene
                self.detection_threshold = float(scn.get("tco_detect_thr", self.detection_threshold or 0.75))
                self.last_detect_new_count = new_cnt
                self.last_detect_margin = int(scn.get("tco_detect_margin", 0))
                md_detect = int(rd.get("min_distance_px", 0))
                if md_detect <= 0:
                    md_detect = int(scn.get("tco_detect_min_distance", 0) or 0)
                if md_detect <= 0:
                    md_detect = int(scn.get("min_distance_base", 0) or 0)
                if md_detect <= 0:
                    md_detect = 200
                self.last_detect_min_distance = int(md_detect)
                scn["kc_min_distance_effective"] = int(md_detect)
            except Exception:
                pass
            try:
                clip = _resolve_clip(context)
                post_ptrs = {int(t.as_pointer()) for t in getattr(clip.tracking, "tracks", [])}
                base = self.pre_ptrs or set()
                # Korrektur: Das hier passiert direkt NACH dem Detect-Call.
                print(f"[COORD] Post Detect: new_after={len(post_ptrs - base)}")
            except Exception:
                pass
            try:
                src = "rd"
                if int(rd.get("min_distance_px", 0) or 0) <= 0:
                    src = "tco|base"
                print(f"[COORD] Detect result: frame={self.target_frame} "
                      f"new={new_cnt} thr->{float(self.detection_threshold):.6f} "
                      f"min_distance->{int(self.last_detect_min_distance)} src={src}")
            except Exception:
                pass
            self.report({'INFO'}, f"DETECT @f{self.target_frame}: new={new_cnt}, thr={self.detection_threshold}")
            self.phase = PH_DISTANZE
            return {'RUNNING_MODAL'}

        # PHASE 4: DISTANZE
        if self.phase == PH_DISTANZE:
            if self.pre_ptrs is None or self.target_frame is None:
                return self._finish(context, info="DISTANZE: Pre-Snapshot oder Ziel-Frame fehlt.", cancelled=True)
            try:
                cur_frame = int(self.target_frame)
                scn = getattr(context, "scene", None)
                eff_md = int(
                    getattr(self, "last_detect_min_distance", 0)
                    or (scn.get("kc_min_distance_effective", 0) if scn else 0)
                    or 200
                )
                print(f"[COORD] Calling Distanz: frame={cur_frame}, min_distance={eff_md}")
                info = run_distance_cleanup(
                    context,
                    baseline_ptrs=self.pre_ptrs,  # zwingt Distanz(e) auf Snapshot-Pfad (kein Selektion-Fallback)
                    frame=cur_frame,
                    min_distance=int(eff_md),
                    distance_unit="pixel",
                    require_selected_new=True,
                    include_muted_old=False,
                    select_remaining_new=True,
                    verbose=True,
                )
            except Exception as exc:
                return self._finish(context, info=f"DISTANZE FAILED â†’ {exc}", cancelled=True)

            if callable(run_count_tracks):
                try:
                    count_result = run_count_tracks(context, frame=int(self.target_frame))  # type: ignore
                except Exception as exc:
                    count_result = {"status": "ERROR", "reason": str(exc)}
            else:
                clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)
                cur = 0
                if clip:
                    for t in getattr(clip.tracking, "tracks", []):
                        try:
                            m = t.markers.find_frame(int(self.target_frame), exact=True)
                        except TypeError:
                            m = t.markers.find_frame(int(self.target_frame))
                        if m and not getattr(t, "mute", False) and not getattr(m, "mute", False):
                            cur += 1
                count_result = {"count": cur}

            ok = str(info.get("status")) == "OK"
            _solve_log(context, {"phase": "DISTANZE", "ok": ok, "info": info, "count": count_result})

            raw_deleted = info.get("deleted", []) or []
            def _label(x):
                if isinstance(x, dict):
                    return x.get("track") or f"ptr:{x.get('ptr')}"
                if isinstance(x, (int, float)):
                    return f"ptr:{int(x)}"
                return str(x)
            deleted_labels = [_label(x) for x in (raw_deleted if isinstance(raw_deleted, (list, tuple)) else [raw_deleted])]
            payload = {"deleted_tracks": deleted_labels, "deleted_count": len(deleted_labels)}
            if deleted_labels:
                _solve_log(context, {"phase": "DISTANZE", **payload})

            removed = info.get("removed", 0)
            kept = info.get("kept", 0)

            # NUR neue Tracks berÃ¼cksichtigen, die AM target_frame einen Marker besitzen
            new_ptrs_after_cleanup: set[int] = set()
            clip = _resolve_clip(context)
            if clip and isinstance(self.pre_ptrs, set):
                trk = getattr(clip, "tracking", None)
                if trk and hasattr(trk, "tracks"):
                    for t in trk.tracks:
                        ptr = int(t.as_pointer())
                        if ptr in self.pre_ptrs:
                            continue  # nicht neu
                        try:
                            m = t.markers.find_frame(int(self.target_frame), exact=True)
                        except TypeError:
                            # Ã¤ltere Blender-Builds ohne exact-Param
                            m = t.markers.find_frame(int(self.target_frame))
                        if m:
                            new_ptrs_after_cleanup.add(ptr)

            # Markeranzahl auswerten, sofern die ZÃ¤hlfunktion vorhanden ist.
            eval_res = None
            scn = context.scene
            if evaluate_marker_count is not None:
                try:
                    # Aufruf ohne explizite Grenzwerte â€“ count.py kennt diese selbst.
                    eval_res = evaluate_marker_count(new_ptrs_after_cleanup=new_ptrs_after_cleanup)  # type: ignore
                except Exception as exc:
                    # Wenn der Aufruf fehlschlÃ¤gt, Fehlermeldung zurÃ¼ckgeben.
                    eval_res = {"status": "ERROR", "reason": str(exc), "count": len(new_ptrs_after_cleanup)}
                # NEU: Count aus count.py global bereitstellen, damit die Formeln
                # im nächsten Detect-Pass NUR diesen Wert verwenden.
                try:
                    bpy.context.scene["tco_count_for_formulas"] = int(eval_res.get("count", 0))
                except Exception:
                    bpy.context.scene["tco_count_for_formulas"] = 0

                # Optional: Telemetrie für Debug/Logs
                _log(
                    f"[COUNT] effective={bpy.context.scene['tco_count_for_formulas']} "
                    f"band=({eval_res.get('min')},{eval_res.get('max')}) status={eval_res.get('status')}"
                )

                # Ergebnis im Szenen-Status speichern
                try:
                    scn["tco_last_marker_count"] = eval_res
                except Exception:
                    pass

                # PrÃ¼fe, ob Markeranzahl auÃŸerhalb des gÃ¼ltigen Bandes liegt
                status = str(eval_res.get("status", "")) if isinstance(eval_res, dict) else ""
                if status in {"TOO_FEW", "TOO_MANY"}:
                    # *** DistanzÃ©-Semantik: nur den MARKER am aktuellen Frame lÃ¶schen ***
                    deleted_markers = 0
                    if clip and new_ptrs_after_cleanup:
                        trk = getattr(clip, "tracking", None)
                        if trk and hasattr(trk, "tracks"):
                            curf = int(self.target_frame)
                            # Variante 1 (bevorzugt): via Operator im CLIP-Override (robust wie UI)
                            try:
                                # Selektion vorbereiten
                                target_ptrs = set(new_ptrs_after_cleanup)
                                for t in trk.tracks:
                                    try:
                                        t.select = False
                                    except Exception:
                                        pass
                                for t in trk.tracks:
                                    if int(t.as_pointer()) in target_ptrs:
                                        try:
                                            t.select = True
                                        except Exception:
                                            pass
                                # Frame sicher setzen
                                try:
                                    scn.frame_set(curf)
                                except Exception:
                                    pass
                                override = _ensure_clip_context(context)
                                if override:
                                    with bpy.context.temp_override(**override):
                                        bpy.ops.clip.delete_marker(confirm=False)
                                else:
                                    bpy.ops.clip.delete_marker(confirm=False)
                                deleted_markers = len(target_ptrs)
                            except Exception:
                                # Variante 2 (Fallback): direkte API, ggf. mehrfach lÃ¶schen bis leer
                                for t in trk.tracks:
                                    if int(t.as_pointer()) in new_ptrs_after_cleanup:
                                        while True:
                                            try:
                                                _m = None
                                                try:
                                                    _m = t.markers.find_frame(curf, exact=True)
                                                except TypeError:
                                                    _m = t.markers.find_frame(curf)
                                                if not _m:
                                                    break
                                                t.markers.delete_frame(curf)
                                                deleted_markers += 1
                                            except Exception:
                                                break
                            # Flush/Refresh, damit der Effekt sofort greift
                            try:
                                bpy.context.view_layer.update()
                                scn.frame_set(curf)
                            except Exception:
                                pass

                    # Threshold neu berechnen:
                    # threshold = max(detection_threshold * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)
                    try:
                        anzahl_neu = float(eval_res.get("count", 0))
                        marker_min = float(eval_res.get("min", 0))
                        marker_max = float(eval_res.get("max", 0))
                        # bevorzugt aus Szene (falls gesetzt), sonst Mittelwert
                        marker_adapt = float(scn.get("marker_adapt", 0.0)) or ((marker_min + marker_max) / 2.0)
                        if marker_adapt <= 0.0:
                            marker_adapt = 1.0
                        base_thr = float(self.detection_threshold if self.detection_threshold is not None
                                         else scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
                        self.detection_threshold = max(base_thr * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)

                        # (entfernt) Szene-Overrides fÃ¼r margin/min_distance â€“ Variablen hier nicht definiert
                    except Exception:
                        pass

                    self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res}, count={count_result}, deleted_markers={deleted_markers}, thrâ†’{self.detection_threshold}")
                    # ZurÃ¼ck zu DETECT mit neuem Threshold
                    self.phase = PH_DETECT
                    return {'RUNNING_MODAL'}


                # Markeranzahl im gÃ¼ltigen Bereich â€“ optional Multi-Pass und dann Bidirectional-Track ausfÃ¼hren.
                did_multi = False
                # NEU: Multi-Pass nur, wenn der *aktuelle* count (aus JSON) >= 6
                wants_multi = False
                try:
                    _state = _get_state(context)
                    _entry, _ = _ensure_frame_entry(_state, int(self.target_frame))
                    _cnt_now = int(_entry.get("count", 1))
                    self.repeat_count_for_target = _cnt_now  # fÃ¼r Logging/UI spiegeln
                    wants_multi = (_cnt_now >= 6)
                except Exception:
                    wants_multi = False
                # Suppress console output using the no-op logger
                _log(f"[Coordinator] multi gate @frame={self.target_frame} count={self.repeat_count_for_target} â†’ wants_multi={wants_multi}")
                if isinstance(eval_res, dict) and str(eval_res.get("status", "")) == "ENOUGH" and wants_multi:
                    # FÃ¼hre nur Multiâ€‘Pass aus, wenn der Helper importiert werden konnte.
                    if run_multi_pass is not None:
                        try:
                            # Snapshot der aktuellen Trackerâ€‘Pointer als Basis fÃ¼r den Multiâ€‘Pass.
                            current_ptrs = set(_snapshot_track_ptrs(context))
                            try:
                                clip = _resolve_clip(context)
                                print(
                                    f"[COORD] Pre Detect/Multi: tracks={len(getattr(clip.tracking,'tracks',[]))} "
                                    f"snapshot_size={len(current_ptrs)} frame={self.target_frame}"
                                )
                            except Exception:
                                pass
                            # Ermittelten Threshold fÃ¼r den Multiâ€‘Pass verwenden. Fallback auf einen Standardwert.
                            try:
                                thr = float(self.detection_threshold) if self.detection_threshold is not None else None
                            except Exception:
                                thr = None
                            if thr is None:
                                try:
                                    thr = float(context.scene.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
                                except Exception:
                                    thr = 0.5
                            # NEU: WiederholungszÃ¤hler an multi.py Ã¼bergeben.
                            mp_res = run_multi_pass(
                                context,
                                detect_threshold=float(thr),
                                pre_ptrs=current_ptrs,
                                repeat_count=int(self.repeat_count_for_target or 0),
                            )
                            try:
                                post_tracks = list(getattr(clip.tracking, "tracks", []))
                                post_ptrs = {int(t.as_pointer()) for t in post_tracks}
                                new_ptrs = post_ptrs - current_ptrs
                                sel_new = [
                                    t for t in post_tracks if int(t.as_pointer()) in new_ptrs and getattr(t, "select", False)
                                ]
                                print(
                                    f"[COORD] Post Multi: total_tracks={len(post_tracks)} new_tracks={len(new_ptrs)} "
                                    f"selected_new={len(sel_new)} (expect selected_new≈new_tracks)"
                                )
                            except Exception:
                                pass
                            try:
                                context.scene["tco_last_multi_pass"] = mp_res  # type: ignore
                            except Exception:
                                pass
                            self.report({'INFO'}, (
                                "MULTI-PASS ausgefÃ¼hrt "
                                f"(rep={self.repeat_count_for_target}): "
                                f"scales={mp_res.get('scales_used')}, "
                                f"created={mp_res.get('created_per_scale')}, "
                                f"selected={mp_res.get('selected')}"
                            ))
                            # Nach dem Multiâ€‘Pass eine DistanzprÃ¼fung durchfÃ¼hren.
                            try:
                                cur_frame = int(self.target_frame) if self.target_frame is not None else None
                                if cur_frame is not None:
                                    scn = getattr(context, "scene", None)
                                    eff_md2 = int(
                                        getattr(self, "last_detect_min_distance", 0)
                                        or (scn.get("kc_min_distance_effective", 0) if scn else 0)
                                        or 200
                                    )
                                    print(f"[COORD] Calling Distanz: frame={cur_frame}, min_distance={eff_md2}")
                                    dist_res = run_distance_cleanup(
                                        context,
                                        baseline_ptrs=current_ptrs,  # zwingt Distanz(e) auf Snapshot-Pfad (kein Selektion-Fallback)
                                        frame=cur_frame,
                                        min_distance=int(eff_md2),
                                        distance_unit="pixel",
                                        require_selected_new=True,
                                        include_muted_old=False,
                                        select_remaining_new=True,
                                        verbose=True,
                                    )
                                    try:
                                        context.scene["tco_last_multi_distance_cleanup"] = dist_res  # type: ignore
                                    except Exception:
                                        pass
                                    self.report({'INFO'}, f"MULTI-PASS DISTANZE: removed={dist_res.get('removed')}, kept={dist_res.get('kept')}")
                            except Exception as exc:
                                self.report({'WARNING'}, f"Multi-Pass DistanzÃ©-Aufruf fehlgeschlagen ({exc})")
                            did_multi = True
                        except Exception as exc:
                            # Bei Fehlern im Multiâ€‘Pass nicht abbrechen, sondern warnen.
                            self.report({'WARNING'}, f"Multi-Pass-Aufruf fehlgeschlagen ({exc})")
                    else:
                        # Multiâ€‘Pass ist nicht verfÃ¼gbar (Import fehlgeschlagen)
                        self.report({'WARNING'}, "Multi-Pass nicht verfÃ¼gbar â€“ kein Aufruf durchgefÃ¼hrt")
                    # Wenn ein Multiâ€‘Pass ausgefÃ¼hrt wurde, starte nun die Bidirectionalâ€‘Track-Phase.
                    if did_multi:
                        # Wechsle in die Bidirectionalâ€‘Phase. Die Bidirectionalâ€‘Track-Operation
                        # selbst wird im Modal-Handler ausgelÃ¶st. Nach Abschluss dieser Phase
                        # wird der Zyklus erneut bei PH_FIND_LOW beginnen.
                        self.phase = PH_BIDI
                        self.bidi_started = False
                        self.report({'INFO'}, (
                        f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, "
                        f"count={count_result}, eval={eval_res} â€“ Starte Bidirectional-Track (nach Multi @rep={self.repeat_count_for_target})"
                        ))
                        return {'RUNNING_MODAL'}
                # --- ENOUGH aber KEIN Multi-Pass (repeat < 6) â†’ direkt BIDI starten ---
                if isinstance(eval_res, dict) and str(eval_res.get("status", "")) == "ENOUGH" and not wants_multi:
                    # Multi wird explizit ausgelassen â†’ Margin auf Tracker-Defaults zurÃ¼cksetzen
                    try:
                        _reset_margin_to_tracker_default(context)
                    except Exception as _exc:
                        self.report({'WARNING'}, f"Margin-Reset (skip multi) fehlgeschlagen: {_exc}")
                    # Direkt in die Bidirectional-Phase wechseln
                    self.phase = PH_BIDI
                    self.bidi_started = False
                    self.report({'INFO'}, (
                        f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, "
                        f"count={count_result}, eval={eval_res} – Starte Bidirectional-Track (ohne Multi; rep={self.repeat_count_for_target})"
                    ))
                    return {'RUNNING_MODAL'}

                # In allen anderen Fällen (kein ENOUGH) → Abschluss
                self.report({'INFO'}, (
                    f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, count={count_result}, eval={eval_res} – Sequenz abgeschlossen."
                ))
                return self._finish(context, info="Sequenz abgeschlossen.", cancelled=False)
            # Wenn keine Auswertungsfunktion vorhanden ist, einfach abschließen
            self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, count={count_result}")
            return self._finish(context, info="Sequenz abgeschlossen.", cancelled=False)
        if self.phase == PH_SPIKE_CYCLE:
            scn = context.scene
            thr = float(self.spike_threshold or 100.0)
            # 1) Spike-Filter
            try:
                run_marker_spike_filter_cycle(context, track_threshold=thr)
            except Exception as exc:
                return self._finish(context, info=f"SPIKE_CYCLE spike_filter failed: {exc}", cancelled=True)
            # 2) Segment-/Track-Cleanup
            try:
                clean_short_segments(context, min_len=int(scn.get("tco_min_seg_len", 25)))
            except Exception:
                pass
            try:
                clean_short_tracks(context)
            except Exception:
                pass
            # 3) Split-Cleanup (UI-override, falls verfÃ¼gbar)
            try:
                override = _ensure_clip_context(context)
                space = override.get("space_data") if override else None
                clip = getattr(space, "clip", None) if space else None
                tracks = clip.tracking.tracks if clip else None
                if override and tracks:
                    with bpy.context.temp_override(**override):
                        recursive_split_cleanup(context, **override, tracks=tracks)
            except Exception:
                pass
            # 4) Max-Marker-Frame suchen
            rmax = run_find_max_marker_frame(context)
            if rmax.get("status") == "FOUND":
                # Erfolg â†’ regulÃ¤ren Zyklus neu starten
                reset_for_new_cycle(context)  # Solve-Log bleibt erhalten (kein Bootstrap)
                self.spike_threshold = None
                scn["tco_spike_cycle_finished"] = False
                self.repeat_count_for_target = None
                self.phase = PH_FIND_LOW
                return {'RUNNING_MODAL'}
            # Kein Treffer
            next_thr = thr * 0.9
            if next_thr < 15:
                # Terminalbedingung: Spike-Cycle beendet – ohne Solve-Fallback.
                try:
                    scn["tco_spike_cycle_finished"] = True
                except Exception:
                    pass
                self.report({'INFO'}, 'Spike-Cycle abgeschlossen – kein Solve mehr verfügbar.')
                return self._finish(
                    context,
                    info='Spike-Cycle beendet: kein Low-Marker-Frame gefunden.',
                    cancelled=False,
                )
            # Weiter iterieren
            self.spike_threshold = next_thr
            return {'RUNNING_MODAL'}
        # PHASE 5: Bidirectional-Tracking. Wird aktiviert, nachdem ein Multi-Pass
        # und DistanzÃ© erfolgreich ausgefÃ¼hrt wurden und die Markeranzahl innerhalb des
        # gÃ¼ltigen Bereichs lag. Startet den Bidirectional-Track-Operator und wartet
        # auf dessen Abschluss. Danach wird die Sequenz wieder bei PH_FIND_LOW fortgesetzt.
        if self.phase == PH_BIDI:
            scn = context.scene
            bidi_active = bool(scn.get("bidi_active", False))
            bidi_result = scn.get("bidi_result", "")
            # Operator noch nicht gestartet â†’ starten
            if not self.bidi_started:
                if CLIP_OT_bidirectional_track is None:
                    return self._finish(context, info="Bidirectional-Track nicht verfÃ¼gbar.", cancelled=True)
                try:
                    # Snapshot vor Start (nur ausgewÃ¤hlte Tracks)
                    self.bidi_before_counts = _marker_count_by_selected_track(context)
                    # Starte den Bidirectionalâ€‘Track mittels Operator. Das 'INVOKE_DEFAULT'
                    # sorgt dafÃ¼r, dass Blender den Operator modal ausfÃ¼hrt.
                    bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                    self.bidi_started = True
                    self.report({'INFO'}, "Bidirectional-Track gestartet")
                except Exception as exc:
                    return self._finish(context, info=f"Bidirectional-Track konnte nicht gestartet werden ({exc})", cancelled=True)
                return {'RUNNING_MODAL'}
            # Operator lÃ¤uft â†’ abwarten
            if not bidi_active:
                # Operator hat beendet. PrÃ¼fe Ergebnis.
                if str(bidi_result) != "OK":
                    return self._finish(context, info=f"Bidirectional-Track fehlgeschlagen ({bidi_result})", cancelled=True)
                # NEU: Delta je Marker berechnen und A_k speichern
                try:
                    before = self.bidi_before_counts or {}
                    after = _marker_count_by_selected_track(context)
                    per_marker_frames = _delta_counts(before, after)
                    # Ziel-Frame bestimmen (Fallback auf aktuellen Scene-Frame)
                    f = int(self.target_frame) if self.target_frame is not None else int(context.scene.frame_current)
                    record_bidirectional_result(
                        context,
                        f,
                        per_marker_frames=per_marker_frames,
                        error_value_func=error_value,
                    )
                    self.report({'INFO'}, f"A_k gespeichert @f{f}: sumÎ”={sum(per_marker_frames.values())}")
                except Exception as _exc:
                    self.report({'WARNING'}, f"A_k speichern fehlgeschlagen: {_exc}")
                # Erfolgreich: fÃ¼r die neue Runde zurÃ¼cksetzen
                try:
                    clean_short_tracks(context)
                    self.report({'INFO'}, "Cleanup nach Bidirectional-Track ausgefÃ¼hrt")
                except Exception as exc:
                    self.report({'WARNING'}, f"Cleanup nach Bidirectional-Track fehlgeschlagen: {exc}")
                reset_for_new_cycle(context)  # Solve-Log bleibt erhalten
                self.detection_threshold = None
                self.pre_ptrs = None
                self.target_frame = None
                self.repeat_map = {}
                self.bidi_started = False
                self.bidi_before_counts = None
                self.repeat_count_for_target = None
                self.phase = PH_FIND_LOW
                self.report({'INFO'}, "Bidirectional-Track abgeschlossen â€“ neuer Zyklus beginnt")
                return {'RUNNING_MODAL'}
            # Wenn noch aktiv â†’ weiter warten
            return {'RUNNING_MODAL'}

        # Fallback (unbekannte Phase)
        return self._finish(context, info=f"Unbekannte Phase: {self.phase}", cancelled=True)
        # --- Ende modal() ---

# --- Registrierung ----------------------------------------------------------
def register():
    """Registriert den Trackingâ€‘Coordinator und optional den Bidirectionalâ€‘Track Operator."""
    # Den Bidirectionalâ€‘Track Operator zuerst registrieren, falls verfÃ¼gbar. Dieser
    # kann aus Helper/bidirectional_track.py importiert werden. Wenn der Import
    # fehlschlÃ¤gt, bleibt die Variable None.
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.register_class(CLIP_OT_bidirectional_track)
        except Exception:
            # Ignoriere Fehler, Operator kÃ¶nnte bereits registriert sein
            pass
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    """Deregistriert den Trackingâ€‘Coordinator und optional den Bidirectionalâ€‘Track Operator."""
    try:
        bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
    except Exception:
        pass
    # Optional auch den Bidirectionalâ€‘Track Operator deregistrieren
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
        except Exception:
            pass


# Optional: lokale Tests beim Direktlauf
if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
