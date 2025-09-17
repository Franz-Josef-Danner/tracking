# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py â€“ Streng sequentieller, MODALER Orchestrator
- Phasen: FIND_LOW â†’ JUMP â†’ DETECT â†’ DISTANZE (hart getrennt, seriell)
- Integration von Anzahl/Aâ‚..Aâ‚‰ + Abbruch bei 10 + A_k-Schreiben in BIDI
- Jede Phase startet erst, wenn die vorherige abgeschlossen wurde.
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

# API-Doku: bpy.ops.clip.delete_track (löscht selektierte Tracks)

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

# ---------------------------------------------------------------------------
# Strikter Solve-Eval-Modus: 3x Solve hintereinander, ohne mutierende Helfer
# ---------------------------------------------------------------------------
IN_SOLVE_EVAL: bool = False  # globales Gate: während TRUE keine Cleanups/Detect/Distanz etc.


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


@contextmanager
def solve_eval_mode():
    """Aktiviert harten Eval-Modus: keine mutierenden Helfer, kein Overlay-Noise."""

    global IN_SOLVE_EVAL
    IN_SOLVE_EVAL = True
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = time.perf_counter() - t0
        IN_SOLVE_EVAL = False
        print(f"[SolveEval] Dauer gesamt: {dt:.3f}s")


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
    """
    Führt bis zu 3 Solve-Durchläufe (verschiedene Distortion-Modelle) direkt
    hintereinander aus – ohne jegliche Cleanups, Detect, Distanz, Mute, Split,
    Spike-Filter oder sonstige mutierende Steps.

    Optionales ``rank_callable`` kann verwendet werden, um aus ``(score, model)``
    einen Vergleichswert abzuleiten (z. B. für custom Ranking-Logik).

    Rückgabe: {"model": best_model, "score": best_score,
               "rank_value": rank_value, "trials": N, "duration": s}
    """

    solve_kwargs = solve_kwargs or {}
    t0 = time.perf_counter()
    # best = (rank_value, model, raw_score)
    best: Optional[Tuple[float, Any, float]] = None
    trials = 0
    models = list(candidate_models)

    with phase_lock("SOLVE_EVAL"), undo_off(), solve_eval_mode():
        for model in models:
            if trials >= max_trials or (time.perf_counter() - t0) > time_budget_sec:
                print("[SolveEval] Budget erreicht – abbrechen.")
                break
            # WICHTIG: nur Model setzen + Solve aufrufen. Nichts anderes.
            apply_model(model)
            t1 = time.perf_counter()
            score = do_solve(quick=quick, **solve_kwargs)  # dein solve_camera()-Wrapper
            dt = time.perf_counter() - t1
            rank_value = rank_callable(score, model) if rank_callable else score
            if rank_callable:
                print(
                    f"[SolveEval] {model}: score={score:.6f} rank={rank_value:.6f} dur={dt:.3f}s"
                )
            else:
                print(f"[SolveEval] {model}: score={score:.6f} dur={dt:.3f}s")
            if (best is None) or (rank_value < best[0]):
                best = (rank_value, model, score)
            trials += 1

    return {
        "model": best[1] if best else None,  # Gewinner-Modell
        "score": best[2] if best else float("inf"),  # Roh-Score des Gewinners
        "rank_value": best[0] if best else float("inf"),  # Vergleichswert
        "trials": trials,
        "duration": time.perf_counter() - t0,
    }

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
    """
    Führt NACH abgeschlossener Modell-Evaluierung einen letzten, vollwertigen Solve
    mit aktivierten Intrinsics-Refine-Flags aus:
      - refine_intrinsics_focal_length = True
      - refine_intrinsics_principal_point = True
      - refine_intrinsics_radial_distortion = True

    Parameter:
      model        : Sieger-Modell aus der Eval
      apply_model  : Callable, das das Distortion-Modell setzt
      solve_full   : Optionaler Callable, der einen Voll-Solve ausführt und einen Score liefert.
                     Falls None, wird solve_camera_only(...) verwendet.

    Rückgabe:
      float Score des finalen Solves (falls Helper Score liefert, sonst 0.0 als Fallback).
    """

    if model is None:
        print("[SolveEval][FINAL] Kein Modell übergeben – finaler Refine-Solve wird übersprungen.")
        return float("inf")

    apply_model(model)
    # Spiegel die Flags in die Tracking-Settings (sichtbar im UI)
    _apply_refine_flags(context, focal=True, principal=True, radial=True)
    # Beim FINALEN Refine-Solve soll der avg_error-Gate die Szenen-Variable
    # `error_track` verwenden. Wir setzen dafür transient ein Scene-Flag,
    # das der Post-Solve-Hook auswertet.
    scn = getattr(context, "scene", None) or bpy.context.scene
    _flag_key = "kc_solve_gate_use_error_track"
    score = 0.0
    dt = 0.0
    try:
        try:
            scn[_flag_key] = True
        except Exception:
            pass
        with phase_lock("SOLVE_FINAL"), undo_off():
            t1 = time.perf_counter()
            # bevorzugt: eigener Voll-Solve-Wrapper; Fallback: solve_camera_only(...)
            if solve_full is not None:
                score = solve_full(
                    context,
                    refine_intrinsics_focal_length=True,
                    refine_intrinsics_principal_point=True,
                    refine_intrinsics_radial_distortion=True,
                )
            else:
                # Fallback: direkter Helper-Call; liefert ggf. None → robust auf 0.0 casten
                score = solve_camera_only(
                    context,
                    refine_intrinsics_focal_length=True,
                    refine_intrinsics_principal_point=True,
                    refine_intrinsics_radial_distortion=True,
                ) or 0.0
            dt = time.perf_counter() - t1
    finally:
        # Flag sauber entfernen – unabhängig vom Ergebnis
        try:
            if scn and _flag_key in scn:
                del scn[_flag_key]
        except Exception:
            pass
    print(f"[SolveEval][FINAL] {model}: score={score:.6f} dur={dt:.3f}s")
    return float(score)

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
    """
    Führt back-to-back die Modell-Evaluierung (3× Solve) aus und danach
    EINEN finalen Voll-Solve mit aktivierten Intrinsics-Refine-Flags.
    Eval bleibt strikt read-only; der finale Solve ist getrennt gekapselt.
    Rückgabe enthält Eval- und Final-Score.
    """
    # 1) Eval (read-only, ohne mutierende Helfer)
    eval_result = solve_eval_back_to_back(
        clip=clip,
        candidate_models=candidate_models,
        apply_model=apply_model,
        do_solve=do_solve_quick,
        rank_callable=rank_callable,
        time_budget_sec=time_budget_sec,
        max_trials=max_trials,
        quick=quick,
        solve_kwargs=solve_kwargs,
    )
    # 2) Finaler Refine-Solve (separat, mit allen Intrinsics-Flags)
    final_score = solve_final_refine(
        context=clip if isinstance(clip, bpy.types.Context) else bpy.context,
        model=eval_result["model"],
        apply_model=apply_model,
        solve_full=solve_full,
    )
    return {**eval_result, "final_score": final_score}

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
from ..Helper.solve_camera import solve_camera_only as _solve_camera
from ..Helper.reduce_error_tracks import (
    get_avg_reprojection_error,
    reduce_error_tracks,
    run_reduce_error_tracks,
)
from ..Helper.refine_high_error import start_refine_modal
from ..Helper.solve_eval import (
    SolveConfig,
    SolveMetrics,
    choose_holdouts,
    set_holdout_weights,
    collect_metrics,
    compute_parallax_scores,
    score_metrics,
    trigger_post_solve_quality_check,
)
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

# ---------------------------------------------------------------------------
# Post-Solve Qualitätscheck (Auto-Reduce & Neustart)
# Policy:
#  - Nach JEDEM Solve den avg. Reprojection-Error prüfen.
#  - Schwellwert: Scene['solve_error_threshold'] oder Default 20.0.
#  - Wenn Error > Threshold:
#       • reduce_error_tracks()
#       • reset_for_new_cycle()
#       • run_find_low_marker_frame()
#  - Schutz gegen Endlosschleifen: max. 5 Auto-Reduce-Versuche pro Zyklus.
#  - Im harten Solve-Eval-Modus (IN_SOLVE_EVAL) kein Eingriff.
# ---------------------------------------------------------------------------
# Default-Policy (konservativ, kann über Scene-Props übersteuert werden)
POST_SOLVE_QUALITY_POLICY = {
    "inf_cost": {"cooldown_s": 30, "max_resets": 2},
    "behind_cam": {"cooldown_s": 30, "max_resets": 2, "purge": True},
    # Optional: falls Durchschnittsfehler akzeptabel, nichts tun;
    # sonst einmal gezielt reduzieren (kleines Batch) und erneut versuchen.
    "avg_error": {"threshold_px": "scene.solve_error_threshold", "max_delete": 11},
}


def _resolve_threshold_px(context):
    # Szene-Eigenschaft oder Fallback
    scn = context.scene
    try:
        return float(getattr(scn, "solve_error_threshold", 20.0))
    except Exception:
        return 20.0


def post_solve_quality_check(context):
    """
    Hook nach einem erfolgreichen Solve: prüft Solve-Log (InfCost/BehindCam),
    löscht ggf. Marker/Tracks (mit Guards/Cooldown) und signalisiert dem
    Orchestrator, ob ein Reset → FindLow nötig ist.
    """

    # Policy dynamisch komplettieren (threshold_px kann aus Szene kommen)
    policy = dict(POST_SOLVE_QUALITY_POLICY)
    avg = dict(policy.get("avg_error", {}))
    if isinstance(avg.get("threshold_px"), str):
        avg["threshold_px"] = _resolve_threshold_px(context)
    policy["avg_error"] = avg

    try:
        result = trigger_post_solve_quality_check(context, policy=policy)
        # Erwartete Struktur (Beispiel):
        # {"action":"reset","reason":"InfCost","deleted":15} oder {"action":"continue"}
        if isinstance(result, dict) and result.get("action") == "reset":
            print(f"[SolveCheck] {result.get('reason', 'post-check')} → Reset to FindLow")
            return "RESET_TO_FIND_LOW"
    except Exception as ex:
        print(f"[SolveCheck] post_solve_quality_check failed: {ex!r}")
    return None


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
    prev = int(scn.frame_current)
    try:
        target = _nearest_recon_frame(clip, prev)
        if target is not None and target != prev:
            scn.frame_set(target)
        yield
    finally:
        try:
            if scn.frame_current != prev:
                scn.frame_set(prev)
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


def _reduce_error_tracks_wrapper(context: bpy.types.Context, **kwargs) -> tuple[int, dict[str, Any]]:
    """Normalisiert die Rückgabe von run_reduce_error_tracks."""

    try:
        res = run_reduce_error_tracks(context, **kwargs)
        if isinstance(res, dict):
            return int(res.get("deleted", 0)), dict(res)
        if isinstance(res, (int, float)):
            val = int(res)
            return val, {"deleted": val}
        return 0, {"deleted": 0}
    except IndexError:
        raise
    except Exception as ex:
        print(f"[ReduceDBG] reduce_error_tracks unexpected failure: {ex!r}")
        return 0, {"deleted": 0, "error": repr(ex)}


def _safe_run_reduce_error_tracks(context: bpy.types.Context) -> int:
    """Wrappt run_reduce_error_tracks; fängt IndexError ab und reduziert hart."""

    try:
        deleted, info = _reduce_error_tracks_wrapper(context)
        if isinstance(info, dict) and info.get("error"):
            print(f"[SolveCheck] reduce_error_tracks reported error: {info['error']}")
        return int(deleted)
    except IndexError as ex:
        print(f"[SolveCheck] reduce_error_tracks IndexError abgefangen: {ex!r}")
        return _emergency_reduce_by_error(context, max_to_delete=5)
    except Exception as ex:
        print(f"[SolveCheck] reduce_error_tracks unexpected failure: {ex!r}")
        return 0


def _try_start_refine_high_error(context: bpy.types.Context) -> bool:
    """Start the refine-high-error modal operator with robust fallbacks."""

    try:
        started = bool(start_refine_modal(context))
        if started:
            _schedule_restart_after_refine(context, delay=0.25)
            print("[SolveCheck] refine_high_error modal gestartet.")
            return True
    except Exception as exc:
        print(f"[SolveCheck] refine_high_error start failed: {exc!r}")
    if _safe_run_reduce_error_tracks(context) <= 0:
        print("[SolveCheck] reduce_error_tracks fallback lieferte 0 deletions.")
    try:
        _ensure_scene_active_clip(context)
        reset_for_new_cycle(context, clear_solve_log=False)
        _route_to_find_low(context)
    except Exception as exc3:
        print(f"[SolveCheck] Reset/FindLow fallback failed: {exc3!r}")
    return False


_COST_KEYS = ("reprojection_cost", "proj_cost", "reproject_cost", "cost", "error", "err", "avg_error")


def _is_non_finite(v) -> bool:
    try:
        f = float(v)
        return not math.isfinite(f)
    except Exception:
        return False


def _marker_has_nonfinite_cost(m) -> bool:
    # IDProperties (Custom) bevorzugen
    try:
        for k in _COST_KEYS:
            if k in m.keys() and _is_non_finite(m[k]):
                return True
    except Exception:
        pass
    # Fallback: nichts gefunden
    return False


def _track_is_deletable_without_markers(trk) -> bool:
    """Nur als ultima ratio: Track löschen, wenn er praktisch leer ist."""

    try:
        return len(getattr(trk, "markers", [])) <= 1
    except Exception:
        return False


def _purge_nonfinite_after_solve(context: bpy.types.Context) -> tuple[int, int]:
    """Löscht Marker mit ∞/NaN-Kosten; löscht Tracks nur, wenn deren Marker ∞/NaN zeigen
       oder der Track faktisch leer ist (≤1 Marker).
       Rückgabe: (markers_deleted, tracks_removed)."""

    clip = _ensure_scene_active_clip(context)
    if not clip:
        return (0, 0)

    del_markers = 0
    del_tracks = 0

    for container, trk, is_top in _iter_all_tracks(clip):
        try:
            # (a) Marker-Level (primäre Quelle für ∞/NaN)
            mks = list(getattr(trk, "markers", []))
            bad_frames = []
            for m in mks:
                if _marker_has_nonfinite_cost(m):
                    try:
                        bad_frames.append(int(getattr(m, "frame", 0)))
                    except Exception:
                        pass
            for fr in sorted(set(bad_frames)):
                try:
                    trk.markers.delete_frame(fr)
                    del_markers += 1
                except Exception as ex:
                    print(f"[InfCost][MarkerDel] frame={fr} name={getattr(trk,'name','?')} ex={ex!r}")
            # (b) Track-Level nur, wenn (a) etwas fand ODER Track leer/1 Marker
            if bad_frames or _track_is_deletable_without_markers(trk):
                _select_only_track(clip, container, trk, is_top_level=is_top)
                ov = _find_clip_editor_override(context, clip)
                if ov:
                    with bpy.context.temp_override(**ov):
                        r = bpy.ops.clip.delete_track(confirm=False)
                        if r == {'FINISHED'}:
                            del_tracks += 1
                            continue
                if _delete_track_hard(container, trk, is_top_level=is_top):
                    del_tracks += 1
                else:
                    try:
                        trk.mute = True
                    except Exception:
                        pass
                    print(f"[InfCost][TrackMute] name={getattr(trk,'name','?')}")
        except Exception as ex:
            print(f"[InfCost] scan failed: {ex!r}")

    if del_markers or del_tracks:
        print(f"[InfCost] purged markers={del_markers} tracks={del_tracks}")
    return (del_markers, del_tracks)


# --- Inf-Cost Backoff/Guard --------------------------------------------------
def _infcost_should_purge(
    scene: bpy.types.Scene, clip: Optional[bpy.types.MovieClip]
) -> bool:
    now = time.time()
    if not clip:
        return True
    key = getattr(clip, "name", "∅")
    st = _INFCOST_STATE.get(key, {})
    cooldown_until = float(st.get("cooldown_until", 0.0))
    if now < cooldown_until:
        print(
            "[InfCost][Guard] cooldown active for "
            f"{cooldown_until - now:.1f}s – purge suppressed (global)."
        )
        return False
    return True


def _infcost_on_purge(
    scene: bpy.types.Scene, clip: Optional[bpy.types.MovieClip]
) -> str:
    """Wird aufgerufen, wenn (mk_del+tr_del)>0. Liefert Aktion:
    'reset' | 'reduce_reset' | 'suppress' (kein Reset, 30s Cool-down)."""

    now = time.time()
    if clip is None:
        return "reset"
    key = getattr(clip, "name", "∅")
    st = _INFCOST_STATE.setdefault(
        key, {"streak": 0, "last_ts": 0.0, "cooldown_until": 0.0}
    )
    streak = int(st.get("streak", 0))
    last_ts = float(st.get("last_ts", 0.0))
    if (now - last_ts) <= 10.0:
        streak += 1
    else:
        streak = 1
    st["streak"] = streak
    st["last_ts"] = now
    _INFCOST_STATE[key] = st
    if streak == 1:
        print("[InfCost][Guard] first hit → reset")
        return "reset"
    if streak == 2:
        print("[InfCost][Guard] second hit → reduce+reset")
        return "reduce_reset"
    st["cooldown_until"] = now + 30.0
    _INFCOST_STATE[key] = st
    print("[InfCost][Guard] repeated hits → suppress reset (30s cooldown, global)")
    return "suppress"


def _schedule_restart_after_refine(context: bpy.types.Context, *, delay: float = 0.5) -> None:
    """Wartet, bis der modal laufende refine_high_error-Operator fertig ist, dann Reset→FindLow."""

    try:
        import bpy as _bpy

        scn = context.scene

        def _cb():
            try:
                if scn.get("refine_active"):
                    return 0.25  # weiter pollen
                try:
                    reset_for_new_cycle(context, clear_solve_log=False)
                except Exception:
                    pass
                _route_to_find_low(context)
            finally:
                return None  # Timer beenden

        _bpy.app.timers.register(_cb, first_interval=max(0.05, float(delay)))
    except Exception as _exc:
        print(f"[SolveCheck] Timer-Register fehlgeschlagen: {_exc!r}")


def solve_camera_only(context, *args, **kwargs):
    # Invoke original solve
    res = _solve_camera(context, *args, **kwargs)
    try:
        # Eval-Modus: strikt read-only → kein Auto-Reduce
        if IN_SOLVE_EVAL:
            return res

        scene = getattr(context, "scene", None)
        if scene is None:
            print("[SolveCheck] Kein context.scene – Check übersprungen.")
            return res

        # Vorab: aktiven Clip setzen; ohne Recon auf Clip-Start klemmen
        clip = _ensure_scene_active_clip(context)
        _set_scene_frame_to_nearest_recon_or_start(context)
        # Falls gar keine Reconstruction-Kameras existieren:
        # AE-Polling & Inf-Cost-Purge überspringen → direkter Fallbackpfad.
        if clip and not _has_any_recon_cameras(clip):
            print("[SolveCheck] Keine Reconstruction-Kameras – AE-Polling übersprungen, Fallback-Pfad.")
            _safe_run_reduce_error_tracks(context)
            try:
                reset_for_new_cycle(context, clear_solve_log=False)
                # Nach Reset: bestmöglichen Recon-Frame setzen (falls entstanden)
                _set_scene_frame_to_nearest_recon_or_start(context)
                _route_to_find_low(context)
            except Exception as ex0:
                print(f"[SolveCheck] Reset/FindLow (no-recon) failed: {ex0!r}")
            return res

        # Kurz auf gültige Reconstruction pollen (max. ~2s) und einen Kameraframe sichern
        ae = None
        with _with_valid_camera_frame(context):
            for _ in range(40):
                ae = get_avg_reprojection_error(context)
                if ae is not None and ae > 0.0:
                    break
                time.sleep(0.05)

        if ae is None:
            print("[SolveCheck] Keine auswertbare Reconstruction (ae=None) – refine_high_error + Restart.")
            _set_scene_frame_to_nearest_recon_or_start(context)
            _safe_run_reduce_error_tracks(context)
            try:
                reset_for_new_cycle(context, clear_solve_log=False)
                _set_scene_frame_to_nearest_recon_or_start(context)
                _route_to_find_low(context)
            except Exception as ex3:
                print(f"[SolveCheck] Reset/FindLow fallback failed: {ex3!r}")
            return res

        if ae <= 0.0:
            print("[SolveCheck] Keine auswertbare Reconstruction (ae<=0) – refine_high_error + Restart.")
            _set_scene_frame_to_nearest_recon_or_start(context)
            _safe_run_reduce_error_tracks(context)
            try:
                reset_for_new_cycle(context, clear_solve_log=False)
                _set_scene_frame_to_nearest_recon_or_start(context)
                _route_to_find_low(context)
            except Exception as ex3:
                print(f"[SolveCheck] Reset/FindLow fallback failed: {ex3!r}")
            return res

        # --- Post-Solve Purges (nur mit Recon & valid AE) ---
        # (1) Negative Tiefe / hinter Kamera
        try:
            bm, bt = _purge_negative_depth_bundles(context, max_deletes=25)
            if (bm + bt) > 0:
                action = _infcost_on_purge(scene, clip)
                print(f"[SolveCheck][BehindCam] total_deleted={bm+bt} action={action}")
                _set_scene_frame_to_nearest_recon_or_start(context)
                if action in ("reduce_reset", "reset"):
                    if action == "reduce_reset":
                        _safe_run_reduce_error_tracks(context)
                    try:
                        reset_for_new_cycle(context, clear_solve_log=False)
                    except Exception as exr_bc:
                        print(f"[SolveCheck][BehindCam] reset_for_new_cycle failed: {exr_bc!r}")
                    try:
                        _set_scene_frame_to_nearest_recon_or_start(context)
                        _route_to_find_low(context)
                    except Exception as exf_bc:
                        print(f"[SolveCheck][BehindCam] FindLow routing failed: {exf_bc!r}")
                    return res
        except Exception as ex_bc:
            print(f"[BehindCam] purge failed: {ex_bc!r}")

        # (2) Non-finite Kosten bereinigen (mit Guard/Backoff)
        mk_del = 0
        tr_del = 0
        try:
            if (
                clip
                and _has_any_recon_cameras(clip)
                and (ae is not None and ae > 0.0)
                and _infcost_should_purge(scene, clip)
            ):
                mk_del, tr_del = _purge_nonfinite_after_solve(context)
        except Exception as ex_purge:
            print(f"[InfCost] purge failed: {ex_purge!r}")
        total_del = mk_del + tr_del
        if total_del > 0:
            action = _infcost_on_purge(scene, clip)
            print(f"[SolveCheck][InfCost] total_deleted={total_del} action={action}")
            if action in ("reduce_reset", "reset"):
                if action == "reduce_reset":
                    _safe_run_reduce_error_tracks(context)
                _set_scene_frame_to_nearest_recon_or_start(context)
                try:
                    reset_for_new_cycle(context, clear_solve_log=False)
                except Exception as exr:
                    print(f"[SolveCheck] reset_for_new_cycle failed: {exr!r}")
                try:
                    _set_scene_frame_to_nearest_recon_or_start(context)
                    _route_to_find_low(context)
                except Exception as exf:
                    print(f"[SolveCheck] FindLow routing failed: {exf!r}")
                return res
            # action == "suppress": kein Reset, Cool-down aktiv

        # Gate-Quelle wählen:
        # - Standard: scene.solve_error_threshold (Default 20.0)
        # - Finaler Refine-Solve: scene.error_track (px), getriggert über Scene-Flag
        use_err_track = bool(scene.get("kc_solve_gate_use_error_track", False))
        if use_err_track:
            thr = float(getattr(scene, "error_track", 2.0) or 2.0)
            _thr_src = "scene.error_track"
        else:
            thr = float(
                getattr(scene, "solve_error_threshold", _SOLVE_ERR_DEFAULT_THR)
                or _SOLVE_ERR_DEFAULT_THR
            )
            _thr_src = "scene.solve_error_threshold"
        # 0.0 ist ebenfalls „invalid“ (Reconstruction noch nicht konsistent)
        print(f"[SolveCheck] avg_error={ae:.6f} thr={thr:.6f} src={_thr_src}")
        attempts = int(scene.get("kc_solve_attempts", 0) or 0)
        if ae > thr and attempts < 5:
            scene["kc_solve_attempts"] = attempts + 1
            # --- Empfohlener Ablauf: n_delete = max(10, avg_projection_error / error_track)
            err_track = float(getattr(scene, "error_track", 2.0) or 2.0)
            n_delete = max(10, int(ae / max(1e-6, err_track)))
            print(
                f"[SolveCheck] Über Schwellwert → reduce_error_tracks(max_to_delete={n_delete}) "
                f"(Formel: max(10, {ae:.3f}/{err_track:.3f})) Pass #{attempts+1}"
            )
            deleted, info = _reduce_error_tracks_wrapper(context, max_to_delete=int(n_delete))
            if int(deleted) <= 0:
                print("[SolveCheck] reduce_error_tracks returned 0 deletions.")
            if isinstance(info, dict) and info.get("error"):
                print(f"[SolveCheck] reduce_error_tracks info: {info['error']}")
            try:
                reset_for_new_cycle(context, clear_solve_log=False)
            except Exception:
                pass
            _route_to_find_low(context)
        elif ae > thr:
            print(
                "[SolveCheck] Schwellwert überschritten, max. Auto-Reduce-Versuche erreicht – kein Auto-Restart."
            )
        else:
            scene["kc_solve_attempts"] = 0
        # Abschluss Solve-Phase: Recon-Frame persistieren
        try:
            _set_scene_frame_to_nearest_recon_or_start(context)
        except Exception:
            pass
        try:
            hook_result = post_solve_quality_check(context)
            if hook_result == "RESET_TO_FIND_LOW":
                try:
                    reset_for_new_cycle(context, clear_solve_log=False)
                except Exception as ex_reset:
                    print(f"[SolveCheck] post-check reset failed: {ex_reset!r}")
                _route_to_find_low(context)
        except Exception as ex_hook:
            print(f"[SolveCheck] post_solve_quality_check hook error: {ex_hook!r}")
    except Exception as ex:
        print(f"[SolveCheck] Ausnahme im Post-Solve-Hook: {ex!r}")
    return res

# --- Orchestrator-Phasen ----------------------------------------------------
PH_FIND_LOW   = "FIND_LOW"
PH_JUMP       = "JUMP"
PH_DETECT     = "DETECT"
PH_DISTANZE   = "DISTANZE"
PH_SPIKE_CYCLE = "SPIKE_CYCLE"
PH_SOLVE_EVAL = "SOLVE_EVAL"
# Erweiterte Phase: Bidirectional-Tracking. Wenn der Multiâ€‘Pass und das
# Distanzâ€‘Cleanup erfolgreich durchgefÃ¼hrt wurden, wird diese Phase
# angestoÃŸen. Sie startet den Bidirectionalâ€‘Track Operator und wartet
# auf dessen Abschluss. Danach beginnt der Koordinator wieder bei PH_FIND_LOW.
PH_BIDI       = "BIDI"

# ---- intern: State Keys / Locks -------------------------------------------
_LOCK_KEY = "tco_lock"

# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

def _ensure_clip_context(context: bpy.types.Context) -> dict:
    """Finde einen CLIP_EDITOR und liefere ein temp_override-Dict fÃ¼r Clip-Operatoren."""
    wm = bpy.context.window_manager
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {
                    "window": win,
                    "area": area,
                    "region": region,
                    "space_data": space,
                    "scene": bpy.context.scene,
                }
    return {}

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

# --- Blender 4.4: Refine-Flag direkt in Tracking-Settings spiegeln ----------
def _apply_refine_focal_flag(context: bpy.types.Context, flag: bool) -> None:
    """Setzt movieclip.tracking.settings.refine_intrinsics_focal_length gemÃ¤ÃŸ flag."""
    try:
        clip = _resolve_clip(context)
        tr = getattr(clip, "tracking", None) if clip else None
        settings = getattr(tr, "settings", None) if tr else None
        if settings and hasattr(settings, "refine_intrinsics_focal_length"):
            settings.refine_intrinsics_focal_length = bool(flag)
            _log(f"[Coordinator] refine_intrinsics_focal_length â†’ {bool(flag)}")
        else:
            _log("[Coordinator] WARN: refine_intrinsics_focal_length nicht verfÃ¼gbar")
    except Exception as exc:
        _log(f"[Coordinator] WARN: refine-Flag konnte nicht gesetzt werden: {exc}")

# --- NEU: weitere Refine-Flags spiegeln --------------------------------------
def _apply_refine_principal_flag(context: bpy.types.Context, flag: bool) -> None:
    """Setzt tracking.settings.refine_intrinsics_principal_point gemÃ¤ÃŸ flag."""
    try:
        clip = _resolve_clip(context)
        settings = getattr(getattr(clip, "tracking", None), "settings", None) if clip else None
        if settings and hasattr(settings, "refine_intrinsics_principal_point"):
            settings.refine_intrinsics_principal_point = bool(flag)
            _log(f"[Coordinator] refine_intrinsics_principal_point â†’ {bool(flag)}")
        else:
            _log("[Coordinator] WARN: refine_intrinsics_principal_point nicht verfÃ¼gbar")
    except Exception as exc:
        _log(f"[Coordinator] WARN: principal-point Flag konnte nicht gesetzt werden: {exc}")

def _apply_refine_radial_flag(context: bpy.types.Context, flag: bool) -> None:
    """Setzt tracking.settings.refine_intrinsics_radial_distortion gemÃ¤ÃŸ flag."""
    try:
        clip = _resolve_clip(context)
        settings = getattr(getattr(clip, "tracking", None), "settings", None) if clip else None
        if settings and hasattr(settings, "refine_intrinsics_radial_distortion"):
            settings.refine_intrinsics_radial_distortion = bool(flag)
            _log(f"[Coordinator] refine_intrinsics_radial_distortion â†’ {bool(flag)}")
        else:
            _log("[Coordinator] WARN: refine_intrinsics_radial_distortion nicht verfÃ¼gbar")
    except Exception as exc:
        _log(f"[Coordinator] WARN: radial-distortion Flag konnte nicht gesetzt werden: {exc}")

def _apply_refine_flags(context: bpy.types.Context, *, focal: bool, principal: bool, radial: bool) -> None:
    """Komfort: alle drei Refine-Flags konsistent setzen."""
    _apply_refine_focal_flag(context, focal)
    _apply_refine_principal_flag(context, principal)
    _apply_refine_radial_flag(context, radial)
    
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


# -- Solve-Eval Helpers ------------------------------------------------------

@dataclass(frozen=True)
class _ReconDigest:
    valid: bool
    num_cams: int
    focal: float
    dsum: float
    err_med: float


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

def _bootstrap(context: bpy.types.Context) -> None:
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
        scn["tco_last_marker_helper"] = {"ok": bool(ok), "count": int(count), "info": dict(info) if hasattr(info, "items") else info}
    except Exception as exc:
        scn["tco_last_marker_helper"] = {"status": "FAILED", "reason": str(exc)}
    scn[_LOCK_KEY] = False


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
    # Solve-Retry-State: Wurde bereits mit refine_intrinsics_focal_length=True neu gelÃ¶st?
    # NEU: Wurde bereits die volle Intrinsics-Variante (focal+principal+radial) versucht?
    solve_refine_full_attempted: bool = False
    # Regressionsvergleich: letzter Solve-Avg (None = noch keiner vorhanden)
    prev_solve_avg: float | None = None
    # Guard: Verhindert mehrfaches reduce_error_tracks fÃ¼r denselben avg_err
    last_reduced_for_avg: float | None = None
    # Solve-Eval State
    _tco_state: str | None = None
    _tco_eval_queue: list[tuple[str, int]] | None = None
    _tco_holdouts: dict | None = None
    _tco_solve_digest_before: _ReconDigest | None = None
    _tco_solve_started_at: float = 0.0
    _tco_timeout_sec: float = 30.0
    _tco_last_run_ok: bool = False
    _tco_metrics: list[SolveMetrics] | None = None
    _tco_cfg: SolveConfig | None = None
    _tco_f_nom: float = 0.0
    _tco_cam_defaults: dict[str, float] | None = None
    _tco_current_model: str | None = None
    _tco_current_stage: int = 0
    _tco_best: SolveMetrics | None = None
    _tco_auto_prev: bool = False
    _tco_keyframe_prev: tuple[int, int] | None = None
    def execute(self, context: bpy.types.Context):
        # Bootstrap/Reset
        try:
            _bootstrap(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Bootstrap failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator: Bootstrap OK")

        # Bootstrap: harter Neustart + Solve-Error-Log leeren
        reset_for_new_cycle(context, clear_solve_log=True)
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
        # Solve-Retry-State zurÃ¼cksetzen
        self.solve_refine_attempted = False
        self.solve_refine_full_attempted = False
        self.bidi_before_counts = None
        self.prev_solve_avg = None
        self.last_reduced_for_avg = None
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
                return {'CANCELLED'}
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    # -- Solve-Eval intern -------------------------------------------------
    def _init_solve_eval(self):
        self._tco_state = "EVAL_PREP"
        self._tco_eval_queue = list(self._build_eval_queue())
        self._tco_holdouts = None
        self._tco_solve_digest_before = None
        self._tco_solve_started_at = 0.0
        self._tco_last_run_ok = False
        self._tco_metrics = []
        self._tco_cfg = SolveConfig()
        self._tco_cam_defaults = None
        self._tco_best = None

    def _build_eval_queue(self):
        models = ("POLYNOMIAL", "DIVISION", "BROWN")
        stages = (1, 2)
        for m in models:
            for s in stages:
                yield (m, s)

    def _get_clip(self, context):
        return _resolve_clip(context)

    def _prepare_eval(self, context):
        clip = self._get_clip(context)
        tr = clip.tracking
        obj = tr.objects.active or (tr.objects[0] if len(tr.objects) else None)
        if obj is None:
            raise RuntimeError("No MovieTrackingObject found.")
        cfg = self._tco_cfg or SolveConfig()
        tr_settings = tr.settings
        scores = compute_parallax_scores(clip, delta=cfg.parallax_delta)
        fs, fe = _clip_frame_range(clip)
        self._tco_auto_prev = bool(tr_settings.use_keyframe_selection)
        tr_settings.use_keyframe_selection = False
        if scores:
            f, _ = scores[0]
            obj.keyframe_a = max(int(f - cfg.parallax_delta), int(fs))
            obj.keyframe_b = min(int(f + cfg.parallax_delta), int(fe))
        else:
            mid = (fs + fe) // 2
            obj.keyframe_a = max(fs, mid - cfg.parallax_delta)
            obj.keyframe_b = min(fe, mid + cfg.parallax_delta)
        self._tco_keyframe_prev = (obj.keyframe_a, obj.keyframe_b)
        holdouts = choose_holdouts(
            clip,
            ratio=cfg.holdout_ratio,
            grid=cfg.holdout_grid,
            edge_boost=cfg.holdout_edge_boost,
        )
        self._tco_holdouts = {t: getattr(t, "weight", 1.0) for t in holdouts}
        set_holdout_weights(holdouts, 0.0)
        cam = tr.camera
        self._tco_f_nom = float(getattr(cam, "focal_length", 0.0)) or 0.0
        self._tco_cam_defaults = {
            "distortion_model": cam.distortion_model,
            "focal_length": float(getattr(cam, "focal_length", 0.0)),
            "k1": float(getattr(cam, "k1", 0.0)),
            "k2": float(getattr(cam, "k2", 0.0)),
            "k3": float(getattr(cam, "k3", 0.0)),
            "division_k1": float(getattr(cam, "division_k1", 0.0)),
            "division_k2": float(getattr(cam, "division_k2", 0.0)),
            "brown_k1": float(getattr(cam, "brown_k1", 0.0)),
            "brown_k2": float(getattr(cam, "brown_k2", 0.0)),
            "brown_k3": float(getattr(cam, "brown_k3", 0.0)),
            "brown_k4": float(getattr(cam, "brown_k4", 0.0)),
            "brown_p1": float(getattr(cam, "brown_p1", 0.0)),
            "brown_p2": float(getattr(cam, "brown_p2", 0.0)),
        }

    def _set_refine_stage(self, tr_settings, stage: int):
        flags = set()
        if stage >= 1:
            flags.update({"FOCAL_LENGTH", "RADIAL_K1"})
        if stage >= 2:
            flags.update({"RADIAL_K2"})
        try:
            tr_settings.refine_intrinsics = flags
        except Exception:
            pass

    def _setup_model_refine(self, context, model: str, stage: int):
        clip = self._get_clip(context)
        tr = clip.tracking
        cam = tr.camera
        tr_settings = tr.settings
        defaults = self._tco_cam_defaults or {}
        for attr, val in defaults.items():
            try:
                setattr(cam, attr, val)
            except Exception:
                pass
        cam.distortion_model = model
        self._set_refine_stage(tr_settings, stage)
        self._tco_current_model = model
        self._tco_current_stage = stage

    def _begin_solve(self, context):
        clip = self._get_clip(context)
        self._tco_solve_digest_before = self._recon_digest(clip)
        self._tco_solve_started_at = time.monotonic()
        try:
            solve_camera_only(context)
        except Exception:
            bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        self._tco_state = "WAIT_SOLVE"

    def _recon_digest(self, clip) -> _ReconDigest:
        tr = clip.tracking
        rec = tr.reconstruction
        cam = tr.camera
        model = cam.distortion_model
        if model == 'POLYNOMIAL':
            dsum = float(getattr(cam, "k1", 0.0) + getattr(cam, "k2", 0.0) + getattr(cam, "k3", 0.0))
        elif model == 'DIVISION':
            dsum = float(getattr(cam, "division_k1", 0.0) + getattr(cam, "division_k2", 0.0))
        elif model == 'BROWN':
            dsum = float(
                getattr(cam, "brown_k1", 0.0) + getattr(cam, "brown_k2", 0.0) +
                getattr(cam, "brown_k3", 0.0) + getattr(cam, "brown_k4", 0.0) +
                getattr(cam, "brown_p1", 0.0) + getattr(cam, "brown_p2", 0.0)
            )
        else:
            dsum = 0.0
        tracks = tr.objects.active.tracks if tr.objects.active else tr.tracks
        train_errs = [t.average_error for t in tracks if getattr(t, "weight", 1.0) > 0.5 and t.average_error > 0]
        err_med = sorted(train_errs)[len(train_errs)//2] if train_errs else 0.0
        return _ReconDigest(
            valid=bool(getattr(rec, "is_valid", False)),
            num_cams=int(len(getattr(rec, "cameras", []))),
            focal=float(getattr(cam, "focal_length", 0.0)),
            dsum=float(dsum),
            err_med=float(err_med),
        )

    def _solve_finished(self, context) -> tuple[bool, bool]:
        clip = self._get_clip(context)
        before = self._tco_solve_digest_before
        now = self._recon_digest(clip)
        changed = (now != before)
        ok = (now.valid and now.num_cams > 0)
        timed_out = (time.monotonic() - self._tco_solve_started_at) > self._tco_timeout_sec
        done = changed or timed_out
        return done, (ok and not timed_out)

    def _collect_metrics_current_run(self, context, *, ok: bool):
        cfg = self._tco_cfg or SolveConfig()
        clip = self._get_clip(context)
        cam = clip.tracking.camera
        holdouts = set(self._tco_holdouts.keys()) if self._tco_holdouts else set()
        if ok:
            hold_med, hold_p95, edge_gap, persist = collect_metrics(clip, holdouts, center_box=cfg.center_box)
        else:
            hold_med = hold_p95 = edge_gap = 999.0
            persist = 0.0
        f_solved = float(getattr(cam, "focal_length", 0.0)) or self._tco_f_nom
        fov_dev_norm = abs(f_solved - self._tco_f_nom) / self._tco_f_nom if self._tco_f_nom > 0 else 0.0
        score = score_metrics(hold_med, hold_p95, edge_gap, persist, fov_dev_norm, cfg.score_w)
        if self._tco_metrics is None:
            self._tco_metrics = []
        self._tco_metrics.append(
            SolveMetrics(
                model=self._tco_current_model or "POLYNOMIAL",
                refine_stage=self._tco_current_stage,
                holdout_med_px=hold_med,
                holdout_p95_px=hold_p95,
                edge_gap_px=edge_gap,
                fov_dev_norm=fov_dev_norm,
                persist=persist,
                score=score,
            )
        )

    def _pick_best_run(self):
        if not self._tco_metrics:
            raise RuntimeError("No solve metrics collected")
        return min(self._tco_metrics, key=lambda m: (m.score, m.holdout_p95_px, m.edge_gap_px))

    def _restore_holdouts(self, context):
        if not self._tco_holdouts:
            return
        for t, w in self._tco_holdouts.items():
            try:
                t.weight = w
            except Exception:
                pass
        clip = self._get_clip(context)
        tr_settings = clip.tracking.settings
        tr_settings.use_keyframe_selection = self._tco_auto_prev
        obj = clip.tracking.objects.active or (clip.tracking.objects[0] if clip.tracking.objects else None)
        if obj and self._tco_keyframe_prev:
            obj.keyframe_a, obj.keyframe_b = self._tco_keyframe_prev
        self._tco_holdouts = None

    def _apply_winner_and_start_final(self, context):
        best = self._pick_best_run()
        self._tco_best = best
        self._restore_holdouts(context)
        # 1) Gewonnenes Distortion-Modell setzen (ohne Downranking der Flags)
        clip = self._get_clip(context)
        cam = clip.tracking.camera
        try:
            cam.distortion_model = best.model
        except Exception:
            pass
        # 2) Alle drei Intrinsics-Refine-Flags aktivieren (UI + Solve-Call)
        _apply_refine_flags(context, focal=True, principal=True, radial=True)
        # 3) Finalen Refine-Solve starten – synchron, mit Flags
        try:
            solve_camera_only(
                context,
                refine_intrinsics_focal_length=True,
                refine_intrinsics_principal_point=True,
                refine_intrinsics_radial_distortion=True,
            )
        except Exception:
            # Fallback auf den Operator (nimmt Flags aus tracking.settings mit)
            bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        # 4) State umstellen – der modal()-Loop wartet auf Abschluss
        self._tco_solve_started_at = time.monotonic()
        self._tco_state = "WAIT_FINAL_SOLVE"

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
        if self.phase == PH_SOLVE_EVAL:
            if self._tco_state == 'EVAL_PREP':
                self._prepare_eval(context)
                self._tco_state = 'EVAL_NEXT_RUN'
                return {'RUNNING_MODAL'}

            if self._tco_state == 'EVAL_NEXT_RUN':
                if not self._tco_eval_queue:
                    self._apply_winner_and_start_final(context)
                    return {'RUNNING_MODAL'}
                model, stage = self._tco_eval_queue.pop(0)
                self._setup_model_refine(context, model, stage)
                self._begin_solve(context)
                return {'RUNNING_MODAL'}

            if self._tco_state == 'WAIT_SOLVE':
                done, ok = self._solve_finished(context)
                if not done:
                    return {'RUNNING_MODAL'}
                self._tco_last_run_ok = ok
                self._tco_state = 'COLLECT'
                return {'RUNNING_MODAL'}

            if self._tco_state == 'COLLECT':
                self._collect_metrics_current_run(context, ok=self._tco_last_run_ok)
                self._tco_state = 'EVAL_NEXT_RUN'
                return {'RUNNING_MODAL'}

            if self._tco_state == 'WAIT_FINAL_SOLVE':
                done, ok = self._solve_finished(context)
                if not done:
                    return {'RUNNING_MODAL'}
                best = self._tco_best
                if best:
                    _solve_log(context, {"winner": best.model, "best": best.__dict__, "all": [m.__dict__ for m in self._tco_metrics]})
                    context.scene["tco_last_solve_eval"] = {"winner": best.model, "best": best.__dict__}
                    self.report({'INFO'}, f'Solve-Eval: {best.model} score={best.score:.3f}')
                return self._finish(context, info='Sequenz abgeschlossen.', cancelled=False)
            return {'RUNNING_MODAL'}

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
                # Terminalbedingung: Spike-Cycle beendet â†’ Kamera-Solve starten
                try:
                    scn["tco_spike_cycle_finished"] = True
                except Exception:
                    pass
                try:
                    # Erstlauf: alle Refine-Flags explizit deaktivieren (Variante 0)
                    try: scn["refine_intrinsics_focal_length"] = False
                    except Exception: pass
                    try: scn["refine_intrinsics_principal_point"] = False
                    except Exception: pass
                    try: scn["refine_intrinsics_radial_distortion"] = False
                    except Exception: pass
                    # Direkt in Settings spiegeln
                    _apply_refine_flags(context, focal=False, principal=False, radial=False)
                    # Retry-States zurÃ¼cksetzen
                    self.solve_refine_attempted = False          # Variante 1 (nur Focal) noch offen
                    self.solve_refine_full_attempted = False     # Variante 2 (alle) noch offen
                    # â†’ direkt in die Solve-Evaluation wechseln
                    self._init_solve_eval()
                    self.phase = PH_SOLVE_EVAL
                    return {'RUNNING_MODAL'}
                except Exception as exc:
                    return self._finish(context, info=f"SolveEval Start fehlgeschlagen: {exc}", cancelled=True)
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
