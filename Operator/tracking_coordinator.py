from __future__ import annotations

import gc
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

import bpy
from typing import Any

def _call_op(
    op: str | Any,
    *,
    invoke: bool = False,
    context_override: dict | None = None,
    **kwargs,
) -> dict:
    """
    Ruft einen Blender-Operator auf.
    op: "clip.solve_camera" oder bereits aufgelöster bpy.ops Aufruf.
    invoke: True → 'INVOKE_DEFAULT', sonst 'EXEC_DEFAULT'.
    context_override: optionaler Context-Override (wird via temp_override gesetzt).
    Rückgabe: {'ok': bool, 'result': set(...)|None, 'error': str|None}
    """
    # Operator auflösen
    try:
        if isinstance(op, str):
            mod, name = op.split(".", 1)
            op_callable = getattr(getattr(bpy.ops, mod), name)
        else:
            op_callable = op
    except Exception as exc:
        return {'ok': False, 'result': None, 'error': f'op_resolve: {exc}'}

    mode = 'INVOKE_DEFAULT' if invoke else 'EXEC_DEFAULT'

    # Operator ausführen (mit robustem Context-Override via temp_override)
    try:
        if context_override:
            try:
                with bpy.context.temp_override(**context_override):
                    res = op_callable(mode, **kwargs)
            except TypeError:
                # Fallback, falls temp_override nicht alle Keys akzeptiert
                res = op_callable(mode, **kwargs)
        else:
            res = op_callable(mode, **kwargs)
        res_set = set(res) if not isinstance(res, set) else res
        ok = bool({'FINISHED', 'RUNNING_MODAL'} & res_set)
        return {'ok': ok, 'result': res_set, 'error': None}
    except Exception as exc:
        return {'ok': False, 'result': None, 'error': f'op_call: {exc}'}
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
    Finaler Voll-Solve mit aktivierten Intrinsics-Refine-Flags.
    Danach: klarer Log zum Avg. Reprojection Error.
    """
    if model is None:
        print("[SolveEval][FINAL] Kein Modell übergeben – finaler Refine-Solve wird übersprungen.")
        return float("inf")

    apply_model(model)

    # Intrinsics-Refine im UI spiegeln
    _apply_refine_flags(context, focal=True, principal=True, radial=True)

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
            if solve_full is not None:
                score = solve_full(
                    context,
                    refine_intrinsics_focal_length=True,
                    refine_intrinsics_principal_point=True,
                    refine_intrinsics_radial_distortion=True,
                )
            else:
                # Fallback: interner Helper
                score = solve_camera_only(
                    context,
                    refine_intrinsics_focal_length=True,
                    refine_intrinsics_principal_point=True,
                    refine_intrinsics_radial_distortion=True,
                ) or 0.0
            dt = time.perf_counter() - t1
    finally:
        try:
            if scn and _flag_key in scn:
                del scn[_flag_key]
        except Exception:
            pass

    print(f"[SolveEval][FINAL] {model}: score={score:.6f} dur={dt:.3f}s")

    # --- FINAL: Recon-Introspektion + Average-Error ---
    try:
        clip  = getattr(context, "edit_movieclip", None)
        obj   = clip.tracking.objects.active if clip and clip.tracking.objects else None
        recon = getattr(obj, "reconstruction", None)
        is_valid = bool(getattr(recon, "is_valid", False)) if recon else False
        cams = getattr(recon, "cameras_nr", 0) if recon else 0
        pts  = getattr(recon, "tracks_markers_nr", 0) if recon else 0
        print(f"[SolveEval][FINAL] recon_valid={is_valid} cams={cams} points={pts}")
    except Exception as _e:
        print(f"[SolveEval][FINAL][WARN] recon introspection failed: {_e!r}")

    try:
        ae = get_avg_reprojection_error(context)
        if ae is None or float(ae) <= 0.0:
            print("[SolveEval][FINAL] AverageError: not available (ae<=0)")
        else:
            print(f"[SolveEval][FINAL] AverageError: {float(ae):.6f}")
    except Exception as _exc:
        print(f"[SolveEval][FINAL][WARN] avg_error log skipped: {_exc!r}")

    return float(score)
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
from ..Helper.jump_to_frame import run_jump_to_frame
# Primitive importieren; Orchestrierung (Formel/Freeze) erfolgt hier.
from ..Helper.detect import run_detect_once as _primitive_detect_once
from ..Helper.distanze import run_distance_cleanup
from ..Helper.spike_filter_cycle import run_marker_spike_filter_cycle
from ..Helper.clean_short_segments import clean_short_segments
from ..Helper.clean_short_tracks import clean_short_tracks
from ..Helper.split_cleanup import recursive_split_cleanup
from ..Helper.find_max_marker_frame import run_find_max_marker_frame  # type: ignore
from ..Helper.solve_camera import solve_camera_only as _solve_camera_only
from ..Helper.reduce_error_tracks import (
    get_avg_reprojection_error,
    run_reduce_error_tracks,
)
from ..Helper.solve_eval import (
    SolveConfig,
    SolveMetrics,
    choose_holdouts,
    set_holdout_weights,
    collect_metrics,
    compute_parallax_scores,
    score_metrics,
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
except Exception:
    try:
        from .count import error_value  # type: ignore
        ERROR_VALUE_SRC = ".count.error_value"
    except Exception:
        def error_value(_track): return 0.0  # Fallback
        ERROR_VALUE_SRC = "FALLBACK_ZERO"


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
try:
    from .bootstrap_O import CLIP_OT_bootstrap_cycle  # type: ignore
except Exception:
    CLIP_OT_bootstrap_cycle = None  # type: ignore
try:
    from .find_frame_O import CLIP_OT_find_low_and_jump  # type: ignore
except Exception:
    CLIP_OT_find_low_and_jump = None  # type: ignore
try:
    from .detect_O import CLIP_OT_detect_cycle  # type: ignore
except Exception:
    CLIP_OT_detect_cycle = None  # type: ignore
try:
    from .clean_O import CLIP_OT_clean_cycle  # type: ignore
except Exception:
    CLIP_OT_clean_cycle = None  # type: ignore
try:
    from .solve_O import CLIP_OT_solve_cycle  # type: ignore
except Exception:
    CLIP_OT_solve_cycle = None  # type: ignore
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
_SOLVE_ERR_DEFAULT_THR = 20.0


def _schedule_restart(context: bpy.types.Context, *, delay: float = 0.5) -> None:
    """Planter Neustart nach kurzer Verzögerung (Timer): Reset → FindLow.

    Ohne Abhängigkeit zu einem externen Modal-Operator.
    """

    try:
        def _cb():
            try:
                # Direkt Reset & Low-Marker-Frame suchen
                try:
                    reset_for_new_cycle(context, clear_solve_log=False)
                except Exception:
                    pass
                try:
                    run_find_low_marker_frame(context)
                except Exception:
                    pass
            finally:
                return None  # Timer beenden

        bpy.app.timers.register(_cb, first_interval=max(0.05, float(delay)))
    except Exception as _exc:
        print(f"[SolveCheck] Timer-Register fehlgeschlagen: {_exc!r}")


def solve_camera_only(context, *args, **kwargs):
    # Invoke original solve
    res = _solve_camera_only(context, *args, **kwargs)
    try:
        # Eval-Modus: strikt read-only → kein Auto-Reduce
        if IN_SOLVE_EVAL:
            return res

        scene = getattr(context, "scene", None)
        if scene is None:
            print("[SolveCheck] Kein context.scene – Check übersprungen.")
            return res

        # Kurz auf gültige Reconstruction pollen (max. ~2s)
        ae = None
        for _ in range(40):
            ae = get_avg_reprojection_error(context)
            if ae is not None and ae > 0.0:
                break
            time.sleep(0.05)

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
        if ae is None or float(ae) <= 0.0:
            print("[SolveCheck] Keine auswertbare Reconstruction (ae<=0) – Restart.")
            _schedule_restart(context)
            return res

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
            run_reduce_error_tracks(context, max_to_delete=int(n_delete))
            try:
                reset_for_new_cycle(context, clear_solve_log=False)
            except Exception:
                pass
            try:
                run_find_low_marker_frame(context)
            except Exception:
                pass
        elif ae > thr:
            print(
                "[SolveCheck] Schwellwert überschritten, max. Auto-Reduce-Versuche erreicht – kein Auto-Restart."
            )
        else:
            scene["kc_solve_attempts"] = 0
    except Exception as ex:
        print(f"[SolveCheck] Ausnahme im Post-Solve-Hook: {ex!r}")
    return res

# --- Orchestrator-Phasen ----------------------------------------------------
PH_FIND_LOW   = "FIND_LOW"
PH_JUMP       = "JUMP"
PH_DETECT     = "DETECT"
PH_WAIT_DETECT = "WAIT_DETECT"  # NEU: Warten auf modal laufenden detect_cycle
PH_DISTANZE   = "DISTANZE"
PH_SPIKE_CYCLE = "SPIKE_CYCLE"
PH_SOLVE_EVAL = "SOLVE_EVAL"
# Erweiterte Phase: Bidirectional-Tracking. Wenn der Multiâ€‘Pass und das
# Distanzâ€‘Cleanup erfolgreich durchgeführt wurden, wird diese Phase
# angestoßen. Sie startet den Bidirectionalâ€‘Track Operator und wartet
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
    # GRAB_CURSOR_XY existiert nicht → Validation-Error beim Register.
    # Modalität kommt über modal(); Cursor-Grabbing ist nicht nötig.
    bl_options = {"REGISTER", "UNDO"}

    # — Laufzeit-State (nur Operator, nicht Szene) —
    _timer: object | None = None
    phase: str = PH_FIND_LOW
    target_frame: int | None = None
    repeat_map: dict[int, int] = {}
    pre_ptrs: set[int] | None = None
    repeat_count_for_target: int | None = None
    # Aktueller Detection-Threshold; wird nach jedem Detect-Aufruf aktualisiert.
    detection_threshold: float | None = None
    spike_threshold: float | None = None  # aktueller Spike-Filter-Schwellenwert (temporär)
    # Telemetrie (optional)
    last_detect_new_count: int | None = None
    last_detect_min_distance: int | None = None
    last_detect_margin: int | None = None
    # Retry-Handling für Detect-Phase
    _detect_retries: int = 0
    _detect_max_retries: int = 5
    # NEU: Start-Gate, verhindert Mehrfach-Start des Detect-Operators pro Phase
    _detect_started: bool = False

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
        # Bootstrap via Operator
        if CLIP_OT_bootstrap_cycle is None:
            self.report({'ERROR'}, "Bootstrap-Operator (clip.bootstrap_cycle) nicht verfügbar")
            return {'CANCELLED'}
        _ovr = _ensure_clip_context(context)
        _res = _call_op('clip.bootstrap_cycle', context_override=_ovr)
        if not (_res and _res.get('ok')):
            self.report({'ERROR'}, f"Bootstrap fehlgeschlagen: {(_res or {}).get('error')}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator: Bootstrap via Operator OK")

        # Modal starten
        self.phase = PH_FIND_LOW
        self.target_frame = None
        self.repeat_map = {}
        self.pre_ptrs = None
        # Threshold-Zurücksetzen: beim ersten Detect-Aufruf wird der Standardwert verwendet
        self.detection_threshold = None
        # Bidirectional‑Track ist noch nicht gestartet
        self.spike_threshold = None  # Spike-Schwellenwert zurücksetzen
        # Solve-Retry-State zurücksetzen
        self.solve_refine_attempted = False
        self.solve_refine_full_attempted = False
        self.bidi_before_counts = None
        self.prev_solve_avg = None
        self.last_reduced_for_avg = None
        self.repeat_count_for_target = None
        # Detect-Start-Gate zurücksetzen
        self._detect_started = False
        # Herkunft der Fehlerfunktion einmalig ausgeben (sichtbar im UI)
        try:
            self.report({'INFO'}, f"error_value source: {ERROR_VALUE_SRC}")
            if ERROR_VALUE_SRC == 'FALLBACK_ZERO':
                self.report({'WARNING'}, 'Fallback error_value aktiv (immer 0.0) – bitte Helper/count.py installieren.')
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
        # --- ESC / Abbruch prüfen ---
        if event.type in {'ESC'} and event.value == 'PRESS':
            return self._finish(context, info="ESC gedrückt – Prozess abgebrochen.", cancelled=True)

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
            # Delegiere an den neuen Operator (find_low + jump in einem Schritt)
            if CLIP_OT_find_low_and_jump is not None:
                _ovr = _ensure_clip_context(context)
                _res = _call_op('clip.find_low_and_jump', context_override=_ovr)
                if _res and _res.get('ok'):
                    # Ergebnis lesen (optional)
                    info = context.scene.get('tco_last_findlowjump', {})
                    self.target_frame = int(info.get('frame') or context.scene.frame_current)
                    marker_basis = None
                    marker_count = None
                    all_frame_counts = []
                    try:
                        marker_basis = context.scene.get('marker_basis', None)
                        if marker_basis is None:
                            marker_basis = context.scene.get('marker_adapt', None)
                        if marker_basis is None:
                            marker_basis = 20
                        # Markeranzahl im gefundenen Frame bestimmen
                        clip = _resolve_clip(context)
                        marker_count = 0
                        if clip and self.target_frame:
                            for tr in getattr(clip.tracking, "tracks", []):
                                try:
                                    m = tr.markers.find_frame(self.target_frame)
                                    if m and not getattr(m, "mute", False) and not getattr(tr, "mute", False):
                                        marker_count += 1
                                except Exception:
                                    pass
                        # Für Debug: Markeranzahl für alle Frames im Bereich
                        if clip:
                            fs = int(context.scene.frame_start)
                            fe = int(context.scene.frame_end)
                            for f in range(fs, fe+1):
                                cnt = 0
                                for tr in getattr(clip.tracking, "tracks", []):
                                    try:
                                        m = tr.markers.find_frame(f)
                                        if m and not getattr(m, "mute", False) and not getattr(tr, "mute", False):
                                            cnt += 1
                                    except Exception:
                                        pass
                                all_frame_counts.append((f, cnt))
                    except Exception:
                        pass
                    print(f"[COORD][FindLow] marker_basis={marker_basis} target_frame={self.target_frame} marker_count={marker_count}")
                    print(f"[COORD][FindLow] Marker pro Frame: " + ", ".join([f"f{f}:{c}" for f,c in all_frame_counts]))
                    self.report({'INFO'}, f"FindLow+Jump OK → f{self.target_frame} | marker_basis={marker_basis} | marker_count={marker_count}")
                    self.phase = PH_DETECT
                    return {'RUNNING_MODAL'}
                else:
                    self.report({'WARNING'}, f"find_low_and_jump via operator fehlgeschlagen ({(_res or {}).get('error')}) – Fallback Inline")
            # Fallback: alte Inline-Logik
            res = run_find_low_marker_frame(context)
            st = res.get("status")
            if st == "FAILED":
                return self._finish(context, info=f"FIND_LOW FAILED → {res.get('reason')}", cancelled=True)
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
            # Delegationsmodus überspringt separate Jump-Phase (bereits in find_low_and_jump erledigt)
            self.phase = PH_DETECT
            return {'RUNNING_MODAL'}
        # PHASE 3: DETECT
        if self.phase == PH_DETECT:
            scn = context.scene
            # Failsafe: Wenn das letzte detect_cycle Ergebnis bereits ENOUGH für diesen Frame ist → direkt zu BIDI
            try:
                _res = scn.get('tco_last_detect_cycle', {}) or {}
                _det = _res.get('detect') or {}
                _cnt = _res.get('count') or {}
                _frm = int(_det.get('frame', -9999))
                _status = str(_cnt.get('status', '')).upper()
                _tgt = int(self.target_frame or scn.frame_current)
                if _frm == _tgt and _status == 'ENOUGH':
                    self._detect_retries = 0
                    self._detect_started = False
                    try:
                        self.report({'INFO'}, f"Coordinator: ENOUGH bereits vorhanden @f{_frm} → PH_BIDI")
                    except Exception:
                        pass
                    self.phase = PH_BIDI
                    return {'RUNNING_MODAL'}
            except Exception:
                pass
            # Wenn Detect bereits läuft (Scene-Flag) oder wir ihn in dieser Phase schon gestartet haben → warten
            if bool(scn.get('tco_detect_active', False)) or getattr(self, '_detect_started', False):
                try:
                    self.report({'INFO'}, "Coordinator: detect bereits aktiv → PH_WAIT_DETECT")
                except Exception:
                    pass
                self.phase = PH_WAIT_DETECT
                return {'RUNNING_MODAL'}
            if CLIP_OT_detect_cycle is not None:
                _ovr = _ensure_clip_context(context)
                self.report({'INFO'}, "Coordinator: detect_cycle starten (modal)")
                _res = _call_op('clip.detect_cycle', invoke=True, context_override=_ovr)
                if not (_res and _res.get('ok')):
                    self.report({'WARNING'}, f"detect_cycle via operator fehlgeschlagen ({(_res or {}).get('error')}) – Fallback Inline")
                else:
                    # Operator läuft modal → auf Scene-Flag warten
                    self._detect_started = True
                    try:
                        self.report({'INFO'}, f"Coordinator: detect_cycle RUNNING_MODAL result={list((_res or {}).get('result', []))}")
                    except Exception:
                        pass
                    self.phase = PH_WAIT_DETECT
                    return {'RUNNING_MODAL'}
                # Wenn der Start scheitert, fällt es unten in die Inline‑Logik
            # Fallback: alte Inline-Logik
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
            # Debug: Track/Marker-Dump nach Detect
            try:
                clip = _resolve_clip(context)
                if clip:
                    track_infos = []
                    for tr in getattr(clip.tracking, "tracks", []):
                        try:
                            n = len(tr.markers)
                            track_infos.append(f"{tr.name}({n})")
                        except Exception:
                            track_infos.append(f"{tr.name}(ERR)")
                    print(f"[COORD][DetectO] Tracks nach Detect: {', '.join(track_infos)}")
            except Exception as exc:
                print(f"[COORD][DetectO] Track/Marker-Dump Fehler: {exc}")
            self.phase = PH_DISTANZE
            return {'RUNNING_MODAL'}

        # NEU: Warten auf detect_cycle (modal)
        if self.phase == PH_WAIT_DETECT:
            scn = context.scene
            active = bool(scn.get('tco_detect_active', False))
            if active:
                # weiter warten
                try:
                    self.report({'INFO'}, "Coordinator: waiting for detect_cycle to finish …")
                except Exception:
                    pass
                return {'RUNNING_MODAL'}
            # Detect ist fertig → Ergebnis auswerten
            res = scn.get('tco_last_detect_cycle', {}) or {}
            detect_info = res.get('detect') or {}
            count = res.get('count') or {}
            status = str(count.get('status', '')).upper() if isinstance(count, dict) else ''
            try:
                self.report({'INFO'}, (
                    f"Coordinator: detect_cycle beendet (status={status}) "
                    f"detect={{frame={detect_info.get('frame')}, new={detect_info.get('new_tracks')}, md={detect_info.get('min_distance_px')}}} "
                    f"count={{count={count.get('count')}, band=[{count.get('min')}..{count.get('max')}]}}"
                ))
            except Exception:
                pass
            # Gate für nächste Runde lösen
            self._detect_started = False
            if status == 'ENOUGH':
                self._detect_retries = 0
                try:
                    self.report({'INFO'}, "Coordinator: ENOUGH → Wechsel zu PH_BIDI")
                except Exception:
                    pass
                self.phase = PH_BIDI
                return {'RUNNING_MODAL'}
            if status == 'TOO_FEW':
                self._detect_retries += 1
                try:
                    self.report({'INFO'}, f"Coordinator: TOO_FEW → Retry {self._detect_retries}/{self._detect_max_retries}")
                except Exception:
                    pass
                if self._detect_retries >= self._detect_max_retries:
                    return self._finish(context, info='Detect: max. Wiederholungen erreicht', cancelled=True)
                # erneuter Detect‑Durchlauf
                self.phase = PH_DETECT
                return {'RUNNING_MODAL'}
            # Unbekannter Status → zurück zu DETECT als Fallback
            try:
                self.report({'WARNING'}, f"Coordinator: unbekannter Detect-Status → zurück zu DETECT (status={status})")
            except Exception:
                pass
            self.phase = PH_DETECT
            return {'RUNNING_MODAL'}
        # PHASE 4: DISTANZE
        if self.phase == PH_DISTANZE:
            # Delegationsmodus: Distanzé war Bestandteil des detect_cycle → direkt auslassen
            res = context.scene.get('tco_last_detect_cycle', {}) or {}
            # Falls kein Ergebnis vorliegt, abbrechen
            if not res:
                return self._finish(context, info='DISTANZE: Kein detect_cycle Ergebnis.', cancelled=True)
            # Weiter in BIDI oder Abschluss je nach Count
            count = res.get('count') or {}
            status = str(count.get('status', '')).upper() if isinstance(count, dict) else ''
            if status == 'ENOUGH':
                self.phase = PH_BIDI
                return {'RUNNING_MODAL'}
            # ansonsten zurück zu DETECT (mit Retry-Gate)
            self._detect_retries += 1
            if self._detect_retries >= self._detect_max_retries:
                return self._finish(context, info='DISTANZE: max. Wiederholungen erreicht', cancelled=True)
            self.phase = PH_DETECT
            return {'RUNNING_MODAL'}
        # PHASE 5: Bidirectional-Tracking. Wird aktiviert, nachdem ein Multi-Pass
        # und Distanzé erfolgreich ausgeführt wurden und die Markeranzahl innerhalb des
        # gültigen Bereichs lag. Startet den Bidirectional-Track-Operator und wartet
        # auf dessen Abschluss. Danach wird die Sequenz wieder bei PH_FIND_LOW fortgesetzt.
        if self.phase == PH_BIDI:
            scn = context.scene
            bidi_active = bool(scn.get("bidi_active", False))
            bidi_result = scn.get("bidi_result", "")
            # Operator noch nicht gestartet → starten
            if not self.bidi_started:
                if CLIP_OT_bidirectional_track is None:
                    return self._finish(context, info="Bidirectional-Track nicht verfügbar.", cancelled=True)
                try:
                    # Snapshot vor Start (nur ausgewählte Tracks)
                    self.bidi_before_counts = _marker_count_by_selected_track(context)
                    try:
                        last_res = scn.get('tco_last_detect_cycle', {}) or {}
                        last_cnt = (last_res.get('count') or {}).get('count')
                        last_frm = (last_res.get('detect') or {}).get('frame')
                        self.report({'INFO'}, f"Coordinator: Transition DETECT→BIDI @f{last_frm} count={last_cnt}")
                    except Exception:
                        pass
                    # Initialisiere Scene-Flags für aktiven Lauf
                    try:
                        scn["bidi_active"] = True
                        scn["bidi_result"] = ""
                    except Exception:
                        pass
                    # Starte den Bidirectional‑Track mittels Operator. Das 'INVOKE_DEFAULT'
                    # sorgt dafür, dass Blender den Operator modal ausführt.
                    bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                    self.bidi_started = True
                    self.report({'INFO'}, "Bidirectional-Track gestartet")
                except Exception as exc:
                    return self._finish(context, info=f"Bidirectional-Track konnte nicht gestartet werden ({exc})", cancelled=True)
                return {'RUNNING_MODAL'}
            # Operator läuft → abwarten
            if not bidi_active:
                # Falls Ergebnis noch nicht gesetzt wurde, weiter warten
                if not bidi_result:
                    try:
                        self.report({'INFO'}, "Coordinator: BIDI inactive aber kein Ergebnis – warte…")
                    except Exception:
                        pass
                    return {'RUNNING_MODAL'}
                # Operator hat beendet. Prüfe Ergebnis.
                if str(bidi_result) != "OK":
                    try:
                        self.report({'WARNING'}, f"Bidirectional-Track fehlgeschlagen ({bidi_result})")
                    except Exception:
                        pass
                    return self._finish(context, info="Bidirectional-Track fehlgeschlagen", cancelled=True)
                # Erfolgreich: weiter kursieren
                try:
                    self.report({'INFO'}, "Bidirectional-Track erfolgreich – weiter mit PH_FIND_LOW")
                except Exception:
                    pass
                # Nach jedem BIDI: Marker-Status für alle Frames loggen
                try:
                    clip = _resolve_clip(context)
                    if clip:
                        fs = int(context.scene.frame_start)
                        fe = int(context.scene.frame_end)
                        frame_counts = []
                        for f in range(fs, fe+1):
                            cnt = 0
                            for tr in getattr(clip.tracking, "tracks", []):
                                try:
                                    m = tr.markers.find_frame(f)
                                    if m and not getattr(m, "mute", False) and not getattr(tr, "mute", False):
                                        cnt += 1
                                except Exception:
                                    pass
                            frame_counts.append((f, cnt))
                        print(f"[COORD][BIDI] Marker pro Frame nach BIDI: " + ", ".join([f"f{f}:{c}" for f,c in frame_counts]))
                except Exception:
                    pass
                self.bidi_started = False
                self.phase = PH_FIND_LOW
                return {'RUNNING_MODAL'}


        # PHASE 6: SPIKE_CYCLE
        if self.phase == PH_SPIKE_CYCLE:
            try:
                self.report({'INFO'}, f"Starte Spike-Filter-Cycle mit Schwelle {self.spike_threshold}")
            except Exception:
                pass
            try:
                # Führe Spike-Filter aus (importiert oben)
                run_marker_spike_filter_cycle(context, threshold=self.spike_threshold or 100.0)
            except Exception as exc:
                try:
                    self.report({'WARNING'}, f"Spike-Filter-Cycle Fehler: {exc}")
                except Exception:
                    pass
            # Nach Spike-Filter: weiter zu SOLVE
            self.phase = "PH_SOLVE"
            return {'RUNNING_MODAL'}

        # PHASE 7: SOLVE
        if self.phase == "PH_SOLVE":
            try:
                self.report({'INFO'}, "Starte Solve-Operator")
            except Exception:
                pass
            try:
                # Starte Solve-Operator (sofern vorhanden)
                if hasattr(bpy.ops.clip, 'solve_cycle'):
                    bpy.ops.clip.solve_cycle('INVOKE_DEFAULT')
                else:
                    bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
            except Exception as exc:
                try:
                    self.report({'WARNING'}, f"Solve-Operator Fehler: {exc}")
                except Exception:
                    pass
            # Nach Solve: Beende Modal-Loop
            return self._finish(context, info="Solve abgeschlossen.", cancelled=False)

        # Fallback: Sollte nie erreicht werden
        try:
            self.report({'WARNING'}, f"modal(): Unerwarteter Zustand! phase={getattr(self, 'phase', None)}")
        except Exception:
            pass
        return {'CANCELLED'}