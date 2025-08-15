# Operator/tracking_coordinator.py — Orchestrator mit Solve/Refine/Cleanup-Sequenz & Handoff an Helper/bidirectional_track
import bpy
import time

from ..Helper.marker_helper_main import marker_helper_main
from ..Helper.main_to_adapt import main_to_adapt
from ..Helper.tracker_settings import apply_tracker_settings

LOCK_KEY = "__detect_lock"  # exklusiver Detect-Lock in scene


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Orchestriert Low-Marker-Find, Jump, Detect, Bidirectional-Track (Helper), Cleanup und Solve."""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Pipeline)"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------
    # User Properties
    # ------------------------------------------------------------
    use_apply_settings: bpy.props.BoolProperty(
        name="Apply Tracker Defaults",
        default=True,
        description="Apply tracker settings before running the pipeline",
    )
    do_backward: bpy.props.BoolProperty(
        name="Bidirectional",
        default=True,
        description="Run backward tracking after forward pass (in Helper gesteuert)",
    )
    auto_clean_short: bpy.props.BoolProperty(
        name="Auto Clean Short",
        default=True,
        description="Delete short tracks after bidirectional tracking",
    )
    poll_every: bpy.props.FloatProperty(
        name="Poll Every (s)",
        default=0.05,
        min=0.01,
        description="Modal poll period",
    )

    # Solve/Refine/Cleanup-Optionen
    enable_refine: bpy.props.BoolProperty(
        name="Refine High Error",
        default=True,
        description="Nach erstem Solve die Top-Fehlerframes gezielt verfeinern und danach erneut lösen",
    )
    refine_limit_frames: bpy.props.IntProperty(
        name="Refine Limit Frames",
        default=10, min=0,
        description="Anzahl Frames mit höchstem Fehler, die im Refine adressiert werden",
    )
    projection_cleanup_action: bpy.props.EnumProperty(
        name="Projection Cleanup Action",
        items=[
            ('DELETE_TRACK', "Delete Tracks", "Fehlerhafte Tracks löschen"),
            ('MUTE', "Mute Tracks", "Fehlerhafte Tracks stummschalten"),
        ],
        default='DELETE_TRACK',
        description="Aktion für builtin_projection_cleanup nach zweitem Solve",
    )

    # ------------------------------------------------------------
    # Runtime State
    # ------------------------------------------------------------
    _timer = None
    _state: str = "INIT"
    _detect_attempts: int = 0
    _detect_attempts_max: int = 8
    _jump_done: bool = False
    _repeat_map: dict = None  # Frame→Count (nur via Jump gepflegt)

    def _log(self, msg: str):
        print(f"[Coordinator] {msg}")

    def _activate_flag(self, context):
        try:
            context.scene["orchestrator_active"] = True
        except Exception:
            pass

    def _deactivate_flag(self, context):
        try:
            context.scene["orchestrator_active"] = False
        except Exception:
            pass

    def _remove_timer(self, context):
        try:
            wm = context.window_manager
            if self._timer:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None

    def _cancel(self, context, reason="Cancelled"):
        self._log(f"Abbruch: {reason}")
        self._remove_timer(context)
        try:
            self._deactivate_flag(context)
            context.scene[LOCK_KEY] = False
        except Exception:
            pass
        self._state = "DONE"
        return {'CANCELLED'}

    def _bootstrap(self, context):
        # init interne Flags
        self._state = "INIT"
        self._detect_attempts = 0
        self._detect_attempts_max = 8
        self._jump_done = False
        self._repeat_map = {}

        # Lock sauber initialisieren
        try:
            context.scene[LOCK_KEY] = False
        except Exception:
            pass

        # Preflight-Helper
        try:
            ok, adapt_val, op_result = marker_helper_main(context)
            self._log(f"[MarkerHelper] ok={ok}, adapt={adapt_val}, op_result={op_result}")
        except Exception as ex:
            self._log(f"[MarkerHelper] Fehler: {ex}")

        try:
            res = main_to_adapt(context, use_override=True)
            self._log(f"[MainToAdapt] Übergabe an tracker_settings (Helper) → {res}")
        except Exception as ex:
            self._log(f"[MainToAdapt] Fehler: {ex}")

        if self.use_apply_settings:
            try:
                apply_tracker_settings(context)
            except Exception as ex:
                self._log(f"[TrackerSettings] Fehler beim Anwenden der Defaults: {ex}")

        self._activate_flag(context)
        self._state = "FIND_LOW"

    # ------------------------------------------------------------
    # Blender Hooks
    # ------------------------------------------------------------
    @classmethod
    def poll(cls, context):
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context, event):
        self._bootstrap(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_every, window=context.window)
        context.window_manager.modal_handler_add(self)
        self._log("Start")
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return self.invoke(context, None)

    # ------------------------------------------------------------
    # Modal FSM
    # ------------------------------------------------------------
    def modal(self, context, event):
        # Detect-/Cleanup-Lock respektieren: solange Detect/Cleanup läuft, NICHTS anderes tun
        try:
            if context.scene.get(LOCK_KEY, False):
                return {'RUNNING_MODAL'}
        except Exception:
            pass

        if event.type == 'ESC':
            return self._cancel(context, "ESC gedrückt")

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if not context.area or context.area.type != "CLIP_EDITOR":
            return self._cancel(context, "CLIP_EDITOR-Kontext verloren")

        # --- FSM ---
        if self._state == "INIT":
            self._state = "FIND_LOW"
            return {'RUNNING_MODAL'}

        elif self._state == "FIND_LOW":
            try:
                from ..Helper.find_low_marker_frame import run_find_low_marker_frame
                res = run_find_low_marker_frame(context) or {}
            except Exception as ex:
                self._log(f"[FindLow] Fehler: {ex}")
                res = {"status": "FAILED"}

            st = res.get("status", "FAILED")
            if st == "FOUND":
                context.scene["goto_frame"] = int(res.get("frame", context.scene.frame_current))
                self._jump_done = False
                self._detect_attempts = 0
                self._state = "JUMP"
            elif st == "NONE":
                self._state = "SOLVE"
            else:
                # Fallback: trotzdem Sprung versuchen
                self._jump_done = False
                self._detect_attempts = 0
                self._state = "JUMP"
            return {'RUNNING_MODAL'}

        elif self._state == "JUMP":
            goto = int(context.scene.get("goto_frame", context.scene.frame_current))
            cur = context.scene.frame_current
            if not self._jump_done or goto != cur:
                try:
                    from ..Helper.jump_to_frame import run_jump_to_frame
                    run_jump_to_frame(context, frame=goto)
                except Exception as ex:
                    self._log(f"[Jump] Fehler: {ex}")
                self._jump_done = True
            self._state = "DETECT"
            return {'RUNNING_MODAL'}

        elif self._state == "DETECT":
            goto = int(context.scene.get("goto_frame", context.scene.frame_current))
            try:
                from ..Helper.detect import run_detect_once
                # WICHTIG: Handoff zur Pipeline aktivieren + einmaligen Clean-Schutz nutzen
                res = run_detect_once(context, start_frame=goto, handoff_to_pipeline=True)
            except Exception as ex:
                self._log(f"[Detect] Ausnahme: {ex}")
                res = {"status": "FAILED", "reason": f"exception:{ex}"}

            st = res.get("status", "FAILED")
            if st == "READY":
                self._detect_attempts = 0
                # statt TRACK_FWD/BWD → Handoff an Helper
                self._state = "BIDITRACK"
                return {'RUNNING_MODAL'}

            if st == "RUNNING":
                self._detect_attempts += 1
                if self._detect_attempts >= self._detect_attempts_max:
                    self._log("[Detect] Timebox erreicht – weiter mit BIDITRACK.")
                    self._detect_attempts = 0
                    self._state = "BIDITRACK"
                return {'RUNNING_MODAL'}

            # FAILED → minimalinvasiver Fallback
            self._log(f"[Detect] FAILED – {res.get('reason','')}")
            self._detect_attempts = 0
            self._state = "BIDITRACK"
            return {'RUNNING_MODAL'}

        # --------- NEU: Übergabe an Helper/bidirectional_track ----------
        elif self._state == "BIDITRACK":
            try:
                scn = context.scene
                scn["bidi_active"] = True
                scn["bidi_result"] = ""
                from ..Helper.bidirectional_track import run_bidirectional_track
                run_bidirectional_track(context)  # registriert eigenen Timer und läuft selbständig
            except Exception as ex:
                self._log(f"[BidiTrack] Fehler beim Start: {ex}")
                scn["bidi_active"] = False
                scn["bidi_result"] = "FAILED"
            self._state = "WAIT_BIDI"
            return {'RUNNING_MODAL'}

        elif self._state == "WAIT_BIDI":
            scn = context.scene
            if scn.get("bidi_active", False):
                # Helper läuft noch → weiter warten
                return {'RUNNING_MODAL'}
            # Helper fertig → optional Clean Short, dann weiter
            if self.auto_clean_short:
                self._state = "CLEAN_SHORT"
            else:
                self._state = "FIND_LOW"
            return {'RUNNING_MODAL'}
        # ----------------------------------------------------------------

        elif self._state == "CLEAN_SHORT":
            if self.auto_clean_short:
                try:
                    from ..Helper.clean_short_tracks import clean_short_tracks
                    clean_short_tracks(context, action='DELETE_TRACK')
                except Exception as ex:
                    self._log(f"[CleanShort] Fehler: {ex}")
            # neuer Zyklus
            self._state = "FIND_LOW"
            return {'RUNNING_MODAL'}

        elif self._state == "SOLVE":
            # —— Sequenz: Solve → (Refine) → Solve → Projection-Cleanup (resolve_error) ——
            try:
                from ..Helper import solve_camera as _solve_mod
            except Exception as ex:
                _solve_mod = None
                self._log(f"[Solve] Modul-Import solve_camera fehlgeschlagen: {ex}")

            def _call(fn_name, *args, **kwargs):
                if _solve_mod and hasattr(_solve_mod, fn_name):
                    fn = getattr(_solve_mod, fn_name)
                    return fn(context, *args, **kwargs)
                raise RuntimeError(f"Helper '{fn_name}' nicht verfügbar")

            # 1) erster Solve
            try:
                self._log("[Solve] Solve #1")
                if _solve_mod and hasattr(_solve_mod, "run_solve"):
                    _call("run_solve")
                else:
                    bpy.ops.clip.solve_camera('EXEC_DEFAULT')
            except Exception as ex:
                self._log(f"[Solve] Fehler bei Solve #1: {ex}")

            # 2) optional Refine High Error
            if self.enable_refine:
                try:
                    if _solve_mod and hasattr(_solve_mod, "refine_high_error"):
                        self._log(f"[Solve] Refine High Error (limit_frames={self.refine_limit_frames})")
                        _call("refine_high_error", limit_frames=int(self.refine_limit_frames))
                    elif _solve_mod and hasattr(_solve_mod, "run_refine_on_high_error"):
                        self._log(f"[Solve] Refine High Error (legacy, limit_frames={self.refine_limit_frames})")
                        _call("run_refine_on_high_error", limit_frames=int(self.refine_limit_frames))
                    else:
                        self._log("[Solve] Refine-Helper nicht gefunden – überspringe Refine")
                except Exception as ex:
                    self._log(f"[Solve] Fehler im Refine: {ex}")

                # 3) zweiter Solve nach Refine
                try:
                    self._log("[Solve] Solve #2 (nach Refine)")
                    if _solve_mod and hasattr(_solve_mod, "run_solve"):
                        _call("run_solve")
                    else:
                        bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                except Exception as ex:
                    self._log(f"[Solve] Fehler bei Solve #2: {ex}")

            # 4) Projection-Cleanup falls Fehler > resolve_error
            try:
                thr = float(context.scene.get("resolve_error", 2.0))
            except Exception:
                thr = 2.0

            need_cleanup = False
            try:
                if _solve_mod and hasattr(_solve_mod, "get_current_solve_error"):
                    cur_err = _call("get_current_solve_error")
                else:
                    cur_err = None
                if cur_err is not None:
                    self._log(f"[Solve] aktueller Solve-Error={cur_err:.4f}, Schwellwert resolve_error={thr:.4f}")
                    need_cleanup = (cur_err > thr)
                else:
                    self._log("[Solve] Solve-Error nicht lesbar – überspringe automatische Prüfung")
            except Exception as ex:
                self._log(f"[Solve] Fehler beim Lesen des Solve-Errors: {ex}")

            if need_cleanup:
                try:
                    self._log(f"[Solve] Projection Cleanup (builtin) mit threshold={thr}, action={self.projection_cleanup_action}")
                    if _solve_mod and hasattr(_solve_mod, "builtin_projection_cleanup"):
                        _call("builtin_projection_cleanup",
                              threshold=thr,
                              action=self.projection_cleanup_action)
                    else:
                        bpy.ops.clip.clean_tracks(
                            frames=0,
                            error=thr,
                            action=self.projection_cleanup_action
                        )
                except Exception as ex:
                    self._log(f"[Solve] Fehler beim Projection Cleanup: {ex}")

            # Fallback-Route, falls dedizierte Helfer fehlen:
            if not _solve_mod or (
                not hasattr(_solve_mod, "run_solve") and
                not hasattr(_solve_mod, "builtin_projection_cleanup")
            ):
                try:
                    from ..Helper.solve_camera import run_solve_watch_clean
                    self._log("[Solve] Fallback run_solve_watch_clean()")
                    run_solve_watch_clean(context)
                except Exception:
                    pass

            self._deactivate_flag(context)
            self._state = "DONE"
            return {'FINISHED'}

        elif self._state == "DONE":
            self._remove_timer(context)
            self._deactivate_flag(context)
            try:
                context.scene[LOCK_KEY] = False
            except Exception:
                pass
            return {'FINISHED'}

        return {'RUNNING_MODAL'}
