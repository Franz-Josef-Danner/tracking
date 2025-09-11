"""
tracking_coordinator.py â€“ Streng sequentieller, MODALER Orchestrator
- Phasen: FIND_LOW â†’ JUMP â†’ DETECT â†’ DISTANZE (hart getrennt, seriell)
- Integration von Anzahl/Aâ‚..Aâ‚‰ + Abbruch bei 10 + A_k-Schreiben in BIDI
- Jede Phase startet erst, wenn die vorherige abgeschlossen wurde.
"""

from __future__ import annotations
import bpy
import time
from dataclasses import dataclass

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
from ..Helper.solve_camera import solve_camera_only
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
    orchestrate_on_jump,
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

    # --- Detect-Wrapper: margin/min_distance strikt aus marker_helper_main ---
    # Formel: f = max((anzahl_neu + 0.1) / anzahl_ziel, 0.0001)
    # threshold_next   = max(threshold_curr * f, 0.0001)
    # min_distance_next= min_distance_curr * 0.95            (nur bei Stagnation)
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

        # 2) State laden/übersteuern
        curr_thr = float(scn.get("tco_detect_thr") or scn.get(DETECT_LAST_THRESHOLD_KEY, 0.0018))
        if threshold is not None:
            curr_thr = float(threshold)

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

        # 4) Formel anwenden:
        #    threshold IMMER; min_distance NUR bei Stagnation (jetzt: *0.95)
        factor = max((float(new_count) + 0.1) / float(max(1, target)), 0.0001)
        next_thr = max(curr_thr * factor, 0.0001)

        # min_distance: einfache Dämpfung bei Stagnation – ohne Clamps/Limits.
        next_md = curr_md
        update_md = False
        if last_nc == new_count:
            next_md = float(curr_md) * 0.9
            update_md = (abs(next_md - curr_md) > 1e-12)

        # 5) Persistieren
        scn["tco_last_detect_new_count"] = int(new_count)
        scn["tco_detect_thr"] = float(next_thr)
        # Nur bei Stagnation persistieren; wir speichern den Float-Wert unverändert ab.
        if update_md:
            scn["tco_detect_min_distance"] = float(next_md)
        scn["tco_detect_margin"] = int(fixed_margin)

        _log(
            f"[DETECT] new={new_count} target={target} "
            f"thr->{next_thr:.7f} "
            f"md->{(next_md if last_nc==new_count else curr_md):.6f} "
            f"src={md_source} "
            f"(stagnation={'YES' if last_nc==new_count else 'NO'}; md_updated={'YES' if update_md else 'NO'})"
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
    _tco_solve_digest_before: "_ReconDigest" | None = None
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
        self._setup_model_refine(context, best.model, best.refine_stage)
        self._begin_solve(context)
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

            # NEU: Anzahl/Motion-Model orchestrieren und ggf. bei 10 abbrechen
            try:
                orchestrate_on_jump(context, int(self.target_frame))
                # count prÃ¼fen (orchestrator zeigt bei ==10 bereits Popup)
                _state = _get_state(context)
                _entry, _ = _ensure_frame_entry(_state, int(self.target_frame))
                _count = int(_entry.get("count", 1))
                self.repeat_count_for_target = _count
                # Abbruch erst, wenn tracking_state die globale Schwelle erreicht (inkl. +10 VerlÃ¤ngerung)
                if _count >= ABORT_AT:
                    return self._finish(
                        context,
                        info=f"Abbruch: Frame {self.target_frame} hat {ABORT_AT-1} DurchlÃ¤ufe erreicht.",
                        cancelled=True
                    )
            except Exception as _exc:
                self.report({'WARNING'}, f"Orchestrate on jump warn: {str(_exc)}")

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
                self.last_detect_min_distance = int(scn.get("tco_detect_min_distance", 0))
            except Exception:
                pass
            try:
                clip = _resolve_clip(context)
                post_ptrs = {int(t.as_pointer()) for t in getattr(clip.tracking, "tracks", [])}
                base = self.pre_ptrs or set()
                print(f"[COORD] Post Detect: detect_new={len(post_ptrs - base)}")
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
                print(f"[COORD] Calling Distanz: frame={cur_frame}, min_distance=None")
                info = run_distance_cleanup(
                    context,
                    baseline_ptrs=self.pre_ptrs,  # zwingt Distanz(e) auf Snapshot-Pfad (kein Selektion-Fallback)
                    frame=cur_frame,
                    # min_distance=None â†’ Auto-Ableitung in distanze.py (aus Threshold & scene-base)
                    min_distance=None,
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
                                    print(f"[COORD] Calling Distanz: frame={cur_frame}, min_distance=None")
                                    dist_res = run_distance_cleanup(
                                        context,
                                        baseline_ptrs=current_ptrs,  # zwingt Distanz(e) auf Snapshot-Pfad (kein Selektion-Fallback)
                                        frame=cur_frame,
                                        min_distance=None,
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
            if next_thr < 10:
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
