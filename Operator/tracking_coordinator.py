from __future__ import annotations
"""
Tracking-Orchestrator (STRICT)
------------------------------
Strikter FSM-Ablauf: FIND_LOW → JUMP → DETECT (nur READY/FAILED zählen) → BIDI (modal) → CLEAN_SHORT → Loop.
- Coordinator ruft niemals direkt bpy.ops.clip.track_markers auf, sondern ausschließlich den Helper-Operator
  Helper/bidirectional_track.py (clip.bidirectional_track).
- Detect läuft ggf. mehrfach (RUNNING) im selben State, bis READY/FAILED oder Timebox.
- Nach Detect: einmaliges Clean-Short-Gate (__skip_clean_short_once) setzen, dann Bi-Track starten.
- Erst nach Bi-Track erfolgt Clean-Short.

NEU (Solve-Workflow – angepasst):
- Solve wird weiterhin asynchron per Helper/solve_camera.solve_watch_clean() (INVOKE_DEFAULT) gestartet.
- Anschließend wechselt die FSM in den State SOLVE_WAIT und wartet nicht-blockierend per Timer-Ticks,
  bis eine gültige Reconstruction verfügbar ist. Erst dann wird der Solve-Error bewertet.
- Direkt nach dem ersten Solve-Versuch: Error mit scene.error_track vergleichen:
    1) Ist der Solve-Error > scene.error_track → GENAU EINMAL Helper/refine_high_error.py,
       anschließend erneut Helper/solve_camera.py, wieder in SOLVE_WAIT warten.
    2) Ist der Solve-Error danach IMMER NOCH > scene.error_track → Helper/projection_cleanup_builtin.py
       (mit diesem Solve-Error als Grenzwert) und anschließend zurück zu Helper/find_low_marker_frame.py (State: FIND_LOW).
    3) Ist der Solve-Error ≤ scene.error_track → FINALIZE.

Hinweis:
- Bei FIND_LOW → NONE wird nun zunächst Helper/clean_error_tracks.py gestartet.
  → Hat der Cleaner etwas gelöscht: zurück zu FIND_LOW (ggf. nach mehreren Durchläufen bis stabil).
  → Hat der Cleaner nichts gefunden: weiter zu SOLVE.
"""

import os
from typing import Optional, Dict, Any

import bpy
from ..Helper.triplet_grouping import run_triplet_grouping  # top-level import

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

# Scene Keys
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8

_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"

# Keys für Optimizer-Signal (werden von Helper/jump_to_frame.py gesetzt)
_OPT_REQ_KEY = "__optimize_request"
_OPT_REQ_VAL = "JUMP_REPEAT"
_OPT_FRAME_KEY = "__optimize_frame"

# Solve-Wait: Anzahl der Timer-Ticks (Timer steht auf 0.25 s in invoke())
_SOLVE_WAIT_TICKS_DEFAULT = 48  # ≈ 12 s
_SOLVE_WAIT_TRIES_PER_TICK = 1  # pro Tick nur ein kurzer Versuch (nicht blockierend)

def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


# ---------------------------------------------------------------------------
# Solve-Error Utilities (lokale Hilfen)
# ---------------------------------------------------------------------------

def _get_active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _compute_solve_error(context) -> Optional[float]:
    """Ermittelt den aktuellen Solve-Error aus der aktiven Rekonstruktion.
    Bevorzugt reconstruction.average_error; Fallback: Mittelwert der Kamera-Errors.
    """
    clip = _get_active_clip(context)
    if not clip:
        return None
    try:
        recon = clip.tracking.objects.active.reconstruction
    except Exception:
        return None
    if not getattr(recon, "is_valid", False):
        return None

    if hasattr(recon, "average_error"):
        try:
            return float(recon.average_error)
        except Exception:
            pass

    try:
        errs = [float(c.average_error) for c in getattr(recon, "cameras", [])]
        if not errs:
            return None
        return sum(errs) / len(errs)
    except Exception:
        return None


def _wait_for_reconstruction(context, tries: int = 12) -> bool:
    """Kurzes, synchrones Warten, bis eine gültige Rekonstruktion verfügbar ist."""
    clip = _get_active_clip(context)
    if not clip:
        return False
    for _ in range(max(1, int(tries))):
        try:
            recon = clip.tracking.objects.active.reconstruction
            if getattr(recon, "is_valid", False):
                return True
        except Exception:
            pass
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
    return False


# --- neu: Cleaner robust starten und Anzahl gelöschter Tracks ermitteln ---

def _count_tracks(context) -> int:
    clip = _get_active_clip(context)
    if not clip:
        return 0
    try:
        return len(clip.tracking.tracks)
    except Exception:
        return 0


def _normalize_clean_error_result(res: Any, scene_val: int = 0) -> int:
    """Normalisiert diverse Rückgabeformen von run_clean_error_tracks zu einer Zahl.
    Nutzt bekannte Felder deines Helpers und generische Fallbacks. "scene_val" kann
    einen externen Scene-basierten Zähler (z. B. __clean_error_deleted) repräsentieren.
    """
    if res is None:
        return max(0, int(scene_val))

    count = 0
    if isinstance(res, dict):
        # 1) Explizite Zähler addieren
        for k in ("deleted_tracks", "deleted_markers", "multiscale_deleted", "total_deleted", "num_deleted"):
            try:
                v = int(res.get(k, 0) or 0)
                count += max(0, v)
            except Exception:
                pass
        # 2) Bool-Flag als mind. 1 zählen
        if bool(res.get("deleted_any", False)):
            count = max(count, 1)
        # 3) Generische Fallbacks
        if count == 0:
            for key in ("deleted", "removed", "deleted_count", "num_removed"):
                try:
                    v = int(res.get(key, 0) or 0)
                    count = max(count, v)
                except Exception:
                    pass
    elif isinstance(res, (int, float)):
        count = int(res)

    try:
        sv = int(scene_val or 0)
        count = max(count, sv)
    except Exception:
        pass
    return int(max(0, count))

# -----------------------------------------------------------------------------
# Projection-Cleanup Wrapper: Triplet-Join + Clean-Short danach
# -----------------------------------------------------------------------------

def _run_projection_cleanup(context, error_value: Optional[float]) -> None:
    """Führt zunächst Helper/refine_high_error aus,
    danach Helper/projection_cleanup_builtin und weitere Nacharbeiten.
    """
    # 0) Refine-High-Error vorher anwenden (einfaches Gate gegen Doppelaufrufe)
    gate_key = "__pre_refine_done"
    if not bool(getattr(context.scene, gate_key, False)):
        try:
            from ..Helper.refine_high_error import run_refine_on_high_error  # type: ignore
            print("[Coord] PROJECTION_CLEANUP → pre-refine_high_error()")
            run_refine_on_high_error(context, limit_frames=0, resolve_after=False)
            context.scene[gate_key] = True
        except Exception as ex_ref:
            print(f"[Coord] refine_high_error skipped/failed: {ex_ref!r}")

    # 1) Projection cleanup (wie bisher)
    try:
        from ..Helper.projection_cleanup_builtin import run_projection_cleanup_builtin  # type: ignore
        if error_value is None:
            res = run_projection_cleanup_builtin(
                context,
                error_limit=None,
                wait_for_error=True,
                wait_forever=False,
                timeout_s=20.0,
                action="DELETE_TRACK",
            )
        else:
            res = run_projection_cleanup_builtin(
                context,
                error_limit=float(error_value),
                wait_for_error=False,
                action="DELETE_TRACK",
            )
        print(f"[Coord] PROJECTION_CLEANUP → {res}")
    except Exception as ex_func:
        print(f"[Coord] projection_cleanup function failed: {ex_func!r} → try operator fallback")
        # Operator-Fallback: ohne Warte-Logik (nur mit error_value sinnvoll)
        try:
            if error_value is not None:
                for prop_name in ("clean_error", "error"):  # native Param-Namen probieren
                    try:
                        bpy.ops.clip.clean_tracks(**{prop_name: float(error_value)}, action="DELETE_TRACK")
                        print(f"[Coord] clean_tracks (fallback, {prop_name}={error_value})")
                        break
                    except TypeError:
                        continue
            else:
                print("[Coord] clean_tracks Fallback SKIPPED: kein error_value")
        except Exception as ex_op:
            print(f"[Coord] projection_cleanup fallback launch failed: {ex_op!r}")

    # 2) Triplet-Join – idempotent; wird übersprungen, falls Helper fehlt
    try:
        from ..Helper.triplet_joiner import run_triplet_join  # type: ignore
        res_join = run_triplet_join(context, active_policy="first")
        print(f"[Coord] PROJECTION_CLEANUP → TRIPLET_JOIN: {res_join}")
    except Exception as ex_join:
        print(f"[Coord] PROJECTION_CLEANUP triplet_join skipped/failed: {ex_join!r}")

    # 3) Clean-Short direkt im Anschluss
    try:
        from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore
        frames = int(getattr(context.scene, "frames_track", 25) or 25)
        print(f"[Coord] PROJECTION_CLEANUP → CLEAN_SHORT (frames<{frames}, DELETE_TRACK)")
        clean_short_tracks(
            context,
            min_len=frames,
            action="DELETE_TRACK",
            respect_fresh=True,
            verbose=True,
        )
    except Exception as ex:
        print(f"[Coord] PROJECTION_CLEANUP CLEAN_SHORT failed: {ex!r}")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (STRICT)"
    bl_options = {"REGISTER", "UNDO"}

    use_apply_settings: bpy.props.BoolProperty(  # type: ignore
        name="Apply Tracker Defaults",
        default=True,
    )
    auto_clean_short: bpy.props.BoolProperty(  # type: ignore
        name="Auto Clean Short",
        default=True,
    )

    _timer: Optional[bpy.types.Timer] = None
    _state: str = "INIT"
    _detect_attempts: int = 0
    _jump_done: bool = False
    _repeat_map: Dict[int, int]
    _bidi_started: bool = False
    _solve_wait_ticks: int = 0  # NEU

    # NEU: genau ein REFINE+Retry Solve zulassen
    _solve_retry_done: bool = False

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    # ---------------- Lifecycle ----------------

    def _run_pre_flight_helpers(self, context) -> None:
        # 1) tracker_settings.py
        try:
            from ..Helper.tracker_settings import apply_tracker_settings  # type: ignore
            apply_tracker_settings(context, log=True)
            print("[Coord] BOOTSTRAP → tracker_settings OK")
        except Exception as ex:
            print(f"[Coord] BOOTSTRAP WARN: tracker_settings failed: {ex!r}")
            try:
                bpy.ops.clip.apply_tracker_settings('INVOKE_DEFAULT')
            except Exception:
                pass

        # 2) marker_helper_main.py (zweite Variante)
        try:
            from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
            marker_helper_main(context)
            print("[Coord] BOOTSTRAP → marker_helper_main OK")
        except Exception as ex_func:
            print(f"[Coord] BOOTSTRAP WARN: marker_helper_main failed: {ex_func!r}")
            try:
                bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')
            except Exception:
                pass

        # 3) (optional) Tracker-Defaults anwenden, wenn UI-Option aktiv
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
        _safe_report(self, {"INFO"}, "Coordinator (STRICT) gestartet")
        print("[Coord] START (STRICT Detect→Bidi→CleanShort)")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # Detect-Lock respektieren (kritische Sektion in Helper/detect.py)
        if context.scene.get(_LOCK_KEY, False):
            return {"RUNNING_MODAL"}

        # FSM
        if self._state == "INIT":
            return self._state_init(context)
        elif self._state == "FIND_LOW":
            return self._state_find_low(context)
        elif self._state == "JUMP":
            return self._state_jump(context)
        elif self._state == "DETECT":
            return self._state_detect(context)
        elif self._state == "TRACK":
            return self._state_track(context)
        elif self._state == "CLEAN_SHORT":
            return self._state_clean_short(context)
        elif self._state == "SOLVE":
            return self._state_solve(context)
        elif self._state == "SOLVE_WAIT":  # NEU
            return self._state_solve_wait(context)
        elif self._state == "FINALIZE":
            return self._finish(context, cancelled=False)

        return self._finish(context, cancelled=True)

    # ---------------- Bootstrap ----------------

    def _bootstrap(self, context):
        scn = context.scene
        scn[_LOCK_KEY] = False
        scn[_BIDI_ACTIVE_KEY] = False
        scn[_BIDI_RESULT_KEY] = ""
        # Safety: altes Skip-Gate entfernen, wir arbeiten strikt reihenfolgebasiert
        scn.pop("__skip_clean_short_once", None)
        scn.pop("__pre_refine_done", None)
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False
        self._solve_wait_ticks = 0
        self._solve_retry_done = False

    # ---------------- States ----------------

    def _state_init(self, context):
        print("[Coord] INIT → BOOTSTRAP")
        self._run_pre_flight_helpers(context)
        print("[Coord] BOOTSTRAP → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _run_post_opt_marker_if_needed(self, context) -> None:
        """Falls der Optimizer zuvor gestartet wurde, einmalig Marker-Helper ausführen,
        **bevor** wieder FIND_LOW arbeitet.
        """
        scn = context.scene
        if not scn.get("_OPT_POST_MARKER_PENDING", False):  # Flag kann extern gesetzt werden
            return
        print("[Coord] POST-OPT → run marker_helper_main()")
        try:
            from ..Helper.marker_helper_main import run_marker_helper_main  # type: ignore
            run_marker_helper_main(context)
        except Exception as ex_func:
            print(f"[Coord] marker_helper_main function failed: {ex_func!r} → try operator fallback")
            try:
                bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')
            except Exception as ex_op:
                print(f"[Coord] marker_helper_main launch failed: {ex_op!r}")
        finally:
            scn["_OPT_POST_MARKER_PENDING"] = False
            print("[Coord] POST-OPT → done (flag cleared)")

    def _state_find_low(self, context):
        from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore

        result = run_find_low_marker_frame(context)
        status = str(result.get("status", "FAILED")).upper()

        if status == "FOUND":
            frame = int(result.get("frame", context.scene.frame_current))
            context.scene[_GOTO_KEY] = frame
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FOUND frame={frame} → JUMP")
            self._state = "JUMP"

        elif status == "NONE":
            # Cleaner ist vollständig aus der Funktionsreihe entfernt → direkt zu SOLVE
            print("[Coord] FIND_LOW → NONE → SOLVE (no cleaner)")
            self._state = "SOLVE"

        else:
            context.scene[_GOTO_KEY] = context.scene.frame_current
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FAILED ({result.get('reason', '?')}) → JUMP (best-effort)")
            self._state = "JUMP"

        return {"RUNNING_MODAL"}

    def _state_solve(self, context):
        """Solve-Start (asynchron, INVOKE_DEFAULT) → dann in SOLVE_WAIT wechseln."""
        try:
            from ..Helper.solve_camera import solve_watch_clean  # type: ignore
            print("[Coord] SOLVE → solve_watch_clean()")
            res = solve_watch_clean(context)  # {'RUNNING_MODAL'} erwartet
            print(f"[Coord] SOLVE → solve_watch_clean() returned {res}")
        except Exception as ex:
            print(f"[Coord] SOLVE failed to start: {ex!r}")
            return self._handle_failed_solve(context)

        # SOLVE_WAIT initialisieren (nicht blockierend, Timer-getaktet)
        self._solve_wait_ticks = int(_SOLVE_WAIT_TICKS_DEFAULT)
        # Wichtig: in jeder Solve-Phase (neu gestartet aus FIND_LOW) ist zunächst kein Retry erfolgt
        self._solve_retry_done = False
        self._state = "SOLVE_WAIT"
        return {"RUNNING_MODAL"}

    def _state_solve_wait(self, context):
        """Nicht-blockierendes Warten auf gültige Rekonstruktion, danach Error-Bewertung."""
        if not _wait_for_reconstruction(context, tries=_SOLVE_WAIT_TRIES_PER_TICK):
            self._solve_wait_ticks -= 1
            print(f"[Coord] SOLVE_WAIT → waiting ({self._solve_wait_ticks} ticks left)")
            if self._solve_wait_ticks > 0:
                return {"RUNNING_MODAL"}
            # Timeout → fehlgeschlagen behandeln
            print("[Coord] SOLVE_WAIT → timeout → FAIL-SOLVE fallback")
            return self._handle_failed_solve(context)

        # Rekonstruktion ist gültig → Error auswerten
        threshold = float(getattr(context.scene, "error_track", 2.0) or 2.0)
        current_err = _compute_solve_error(context)
        high_threshold = threshold * 10.0
        print(f"[Coord] SOLVE_WAIT → error={current_err!r} vs. threshold={threshold} (hi={high_threshold})")

        if current_err is None:
            print("[Coord] SOLVE_WAIT → Kein gültiger Error → PROJECTION_CLEANUP (wartend) → FIND_LOW")
            _run_projection_cleanup(context, None)
            self._state = "FIND_LOW"
            self._solve_retry_done = False
            return {"RUNNING_MODAL"}

        # 1) High-Gate: sofortiges Cleanup bei extrem hohem Error
        if current_err > high_threshold:
            print(f"[Coord] SOLVE_WAIT → Error > high_threshold ({current_err} > {high_threshold}) "
                  f"→ PROJECTION_CLEANUP(error_limit={current_err}) → FIND_LOW")
            try:
                _run_projection_cleanup(context, current_err)
            except Exception as ex_cu:
                print(f"[Coord] PROJECTION_CLEANUP failed: {ex_cu!r}")
            self._state = "FIND_LOW"
            self._solve_retry_done = False
            return {"RUNNING_MODAL"}

        # 2) Normales Gate: einmaliger Refine-Retry, danach ggf. Cleanup
        if current_err > threshold:
            if not self._solve_retry_done:
                # Einmaliger Versuch: REFINE → erneut Solve → wieder SOLVE_WAIT
                print("[Coord] SOLVE_WAIT → Error > threshold → REFINE (einmalig) + Retry Solve")
                try:
                    from ..Helper.refine_high_error import run_refine_on_high_error  # type: ignore
                    run_refine_on_high_error(context, limit_frames=0, resolve_after=False)
                except Exception as ex_ref:
                    print(f"[Coord] REFINE failed: {ex_ref!r}")

                try:
                    from ..Helper.solve_camera import solve_watch_clean  # type: ignore
                    print("[Coord] SOLVE_WAIT → retry solve_watch_clean() after REFINE")
                    solve_watch_clean(context)
                except Exception as ex2:
                    print(f"[Coord] SOLVE retry failed: {ex2!r}")

                self._solve_retry_done = True
                self._solve_wait_ticks = int(getattr(context.scene, "solve_wait_ticks", _SOLVE_WAIT_TICKS_DEFAULT))
                return {"RUNNING_MODAL"}

            # Retry wurde bereits gemacht → PROJECTION_CLEANUP mit diesem Error und direkt FIND_LOW
            print(
                f"[Coord] SOLVE_WAIT → Error weiterhin zu hoch ({current_err}) "
                f"→ PROJECTION_CLEANUP(error_limit={current_err}) → FIND_LOW"
            )
            try:
                _run_projection_cleanup(context, current_err)  # error_limit = aktueller Solve-Error
            except Exception as ex_cu:
                print(f"[Coord] PROJECTION_CLEANUP failed: {ex_cu!r}")
            self._state = "FIND_LOW"
            self._solve_retry_done = False
            return {"RUNNING_MODAL"}

        # 3) Fehler unter Schwelle → fertig
        print("[Coord] SOLVE_WAIT → FINALIZE")
        self._state = "FINALIZE"
        self._solve_retry_done = False
        return {"RUNNING_MODAL"}

    def _handle_failed_solve(self, context):
        """Fallback-Pfad, wenn Solve keine gültige Reconstruction erzeugt (z. B. 'No camera for frame')."""
        print("[Coord] FAIL-SOLVE → versuche CleanErrorTracks")

        try:
            from ..Helper.clean_error_tracks import run_clean_error_tracks  # type: ignore
            res = run_clean_error_tracks(context, show_popups=False, soften=0.5)
            deleted_count = _normalize_clean_error_result(res, context.scene.get("__clean_error_deleted", 0))
        except Exception as ex_clean:
            print(f"[Coord] FAIL-SOLVE Cleaner failed: {ex_clean!r}")
            deleted_count = 0

        if deleted_count > 0:
            # Tracks wurden entfernt → zurück zu FIND_LOW
            print(f"[Coord] FAIL-SOLVE → Cleaner deleted {deleted_count} → FIND_LOW restart")
            self._state = "FIND_LOW"
            self._solve_retry_done = False
            return {"RUNNING_MODAL"}

        # Fallback wenn nichts gelöscht wurde → alter Weg (Refine + ProjectionCleanup)
        try:
            from ..Helper.refine_high_error import run_refine_on_high_error  # type: ignore
            print("[Coord] FAIL-SOLVE → Cleaner fand nichts → versuche REFINE (Top-N)")
            run_refine_on_high_error(context, limit_frames=0, resolve_after=False)
        except Exception as ex_ref:
            print(f"[Coord] FAIL-SOLVE REFINE failed: {ex_ref!r}")

        try:
            print("[Coord] FAIL-SOLVE → PROJECTION_CLEANUP (wartend)")
            _run_projection_cleanup(context, None)
        except Exception as ex_cu:
            print(f"[Coord] FAIL-SOLVE CLEANUP failed: {ex_cu!r}")

        self._state = "FIND_LOW"
        self._solve_retry_done = False
        return {"RUNNING_MODAL"}


    def _state_jump(self, context):
        from ..Helper.jump_to_frame import run_jump_to_frame  # type: ignore
        if not self._jump_done:
            goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
            jr = run_jump_to_frame(context, frame=goto, repeat_map=self._repeat_map)
            if jr.get("status") != "OK":
                print(f"[Coord] JUMP failed: {jr.get('reason','?')} → FIND_LOW")
                self._state = "FIND_LOW"
                return {"RUNNING_MODAL"}
            print(f"[Coord] JUMP → frame={jr['frame']} repeat={jr['repeat_count']} → DETECT")

            # Signal aus jump_to_frame verwerten (falls gesetzt)
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
                    start_optimization(context)
                    print(f"[Coord] JUMP → OPTIMIZE (start_optimization, frame={opt_frame})")
                except Exception as ex_func:
                    print(f"[Coord] OPTIMIZE failed (function): {ex_func!r}")
                    try:
                        bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
                        print(f"[Coord] JUMP → OPTIMIZE (operator fallback, frame={opt_frame})")
                    except Exception as ex_op:
                        print(f"[Coord] OPTIMIZE launch failed: {ex_op!r}")

            self._jump_done = True
        self._detect_attempts = 0
        self._state = "DETECT"
        return {"RUNNING_MODAL"}

    def _state_detect(self, context):
        """Nur ein Signal akzeptieren: READY/FAILED → TRACK, RUNNING → im DETECT-State bleiben."""
        from ..Helper.detect import run_detect_once  # type: ignore

        goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
        res = run_detect_once(
            context,
            start_frame=goto,
            handoff_to_pipeline=True,
        )
        status = str(res.get("status", "FAILED")).upper()

        if status == "RUNNING":
            self._detect_attempts += 1
            print(f"[Coord] DETECT → RUNNING (attempt {self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[Coord] DETECT Timebox erreicht → force TRACK")
                self._state = "TRACK"
            return {"RUNNING_MODAL"}

        try:
            tg = run_triplet_grouping(context)
            print(f"[Coord] TRIPLET_GROUPING → {tg}")
        except Exception as ex_tg:
            print(f"[Coord] TRIPLET_GROUPING failed: {ex_tg!r}")

        print(f"[Coord] DETECT → {status} → TRACK (Bidirectional)")
        self._state = "TRACK"
        return {"RUNNING_MODAL"}

    def _state_track(self, context):
        """Startet und überwacht den Bidirectional-Operator. CleanShort kommt erst nach Abschluss."""
        scn = context.scene

        if not self._bidi_started:
            scn[_BIDI_RESULT_KEY] = ""
            scn[_BIDI_ACTIVE_KEY] = False
            print("[Coord] TRACK → launch clip.bidirectional_track (INVOKE_DEFAULT)")
            try:
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                self._bidi_started = True
            except Exception as ex:
                print(f"[Coord] TRACK launch failed: {ex!r} → CLEAN_SHORT (best-effort)")
                self._bidi_started = False
                self._state = "CLEAN_SHORT"
            return {"RUNNING_MODAL"}

        if scn.get(_BIDI_ACTIVE_KEY, False):
            print("[Coord] TRACK → waiting (bidi_active=True)")
            return {"RUNNING_MODAL"}

        scn[_BIDI_RESULT_KEY] = ""
        self._bidi_started = False
        self._state = "CLEAN_SHORT"
        return {"RUNNING_MODAL"}

    def _state_clean_short(self, context):
        """Short-Clean ausschließlich nach Bi-Track."""
        if self.auto_clean_short:
            from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore
            frames = int(getattr(context.scene, "frames_track", 25) or 25)
            print(f"[Coord] CLEAN_SHORT → frames<{frames} (DELETE_TRACK)")
            try:
                clean_short_tracks(
                    context,
                    min_len=frames,
                    action="DELETE_TRACK",
                    verbose=True,
                )
            except Exception as ex:
                print(f"[Coord] CLEAN_SHORT failed: {ex!r}")

        print("[Coord] CLEAN_SHORT → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

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
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)


# ---------------- Self-Tests (reine Python-Checks, laufen nur, wenn explizit aktiviert) ----------------
if __name__ == "__main__" and os.getenv("ADDON_RUN_TESTS", "0") == "1":
    # Die Tests prüfen ausschließlich die Normalisierung der Cleaner-Rückgabe,
    # damit sie ohne Blender-Kontext lauffähig sind.
    test_cases = [
        ("empty dict", {}, 0, 0),
        ("deleted_any", {"status": "FINISHED", "deleted_any": True}, 0, 1),
        ("tracks+markers", {"deleted_tracks": 2, "deleted_markers": 5}, 0, 7),
        ("multiscale_only", {"multiscale_deleted": 3}, 0, 3),
        ("fallback_generic", {"deleted": 4}, 0, 4),
        ("scene_val_override", {}, 2, 2),
        ("mixed_all", {"deleted_tracks": 1, "deleted_markers": 1, "deleted_any": True}, 0, 2),
    ]

    for name, res, scene_val, expected in test_cases:
        got = _normalize_clean_error_result(res, scene_val)
        assert got == expected, f"case '{name}': expected {expected}, got {got}"
    print("[SelfTest] _normalize_clean_error_result: OK (", len(test_cases), "cases )")
