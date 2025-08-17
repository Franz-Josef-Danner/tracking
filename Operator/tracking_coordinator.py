# Operator/tracking_coordinator_detect_only.py
# — Minimaler Orchestrator NUR für Detect-Tests —
# Reihenfolge: Find → Jump → (Wait/Settle) → Sanitize → Detect → DONE
#
# Zweck: die Detect-Funktion gezielt (und wiederholt) testen, ohne BiDi-Tracking,
# CleanShort oder Solve. Der Operator beendet nach einem fertigen Detect-Zyklus.

from __future__ import annotations

import unicodedata
from typing import Dict, Set
import bpy

from ..Helper.marker_helper_main import marker_helper_main
from ..Helper.main_to_adapt import main_to_adapt
from ..Helper.tracker_settings import apply_tracker_settings

LOCK_KEY = "__detect_lock"  # exklusiver Detect-/Cleanup-Lock in scene


# ------------------------------------------------------------
# String-Sanitizer (gegen NBSP/Encoding-Ausreißer)
# ------------------------------------------------------------

def _sanitize_str(s) -> str:
    if isinstance(s, (bytes, bytearray)):
        try:
            s = s.decode("utf-8")
        except Exception:
            s = s.decode("latin-1", errors="replace")
    s = str(s).replace("\u00A0", " ")  # NBSP → Space
    return unicodedata.normalize("NFKC", s).strip()


def _sanitize_all_track_names(context: bpy.types.Context) -> None:
    """Bereinigt sicher alle Track-Namen im aktiven/zugeordneten MovieClip."""
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    if not mc:
        return
    try:
        tracks = mc.tracking.tracks
    except Exception:
        return
    for tr in tracks:
        try:
            tr.name = _sanitize_str(tr.name)
        except Exception:
            pass


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Detect-Only Orchestrator: Find → Jump → Wait → Detect → DONE."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Detect-Only)"
    bl_options = {"REGISTER", "UNDO"}

    # ------------------------------------------------------------
    # User Properties
    # ------------------------------------------------------------
    use_apply_settings: bpy.props.BoolProperty(
        name="Apply Tracker Defaults",
        default=True,
        description="Apply tracker settings before running the pipeline",
    )
    poll_every: bpy.props.FloatProperty(
        name="Poll Every (s)",
        default=0.05,
        min=0.01,
        description="Modal poll period",
    )
    max_detect_attempts: bpy.props.IntProperty(
        name="Max Detect Attempts",
        default=8,
        min=1,
        description="Wie oft Detect erneut versucht wird, wenn RUNNING zurückkommt",
    )
    settle_ticks_after_jump: bpy.props.IntProperty(
        name="Settle Ticks After Jump",
        default=2,
        min=0,
        description="Anzahl Timer-Zyklen, die nach Jump gewartet werden (Depsgraph/Redraw)",
    )

    # ------------------------------------------------------------
    # Runtime State
    # ------------------------------------------------------------
    _timer = None
    _state: str = "INIT"
    _detect_attempts: int = 0
    _jump_done: bool = False
    _settle_ticks: int = 0

    # --------------------------
    # interne Hilfsfunktionen
    # --------------------------
    def _log(self, msg: str) -> None:
        print(f"[Coordinator] {msg}")

    def _activate_flag(self, context: bpy.types.Context) -> None:
        try:
            context.scene["orchestrator_active"] = True
        except Exception:
            pass

    def _deactivate_flag(self, context: bpy.types.Context) -> None:
        try:
            context.scene["orchestrator_active"] = False
        except Exception:
            pass

    def _remove_timer(self, context: bpy.types.Context) -> None:
        try:
            wm = context.window_manager
            if self._timer:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None

    def _finish(self, context: bpy.types.Context, *, cancelled: bool = False) -> Set[str]:
        self._remove_timer(context)
        self._deactivate_flag(context)
        try:
            context.scene[LOCK_KEY] = False
        except Exception:
            pass
        self._state = "DONE"
        return {"CANCELLED" if cancelled else "FINISHED"}

    def _cancel(self, context: bpy.types.Context, reason: str = "Cancelled") -> Set[str]:
        self._log(f"Abbruch: {reason}")
        return self._finish(context, cancelled=True)

    def _bootstrap(self, context: bpy.types.Context) -> None:
        # init interne Flags
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._settle_ticks = 0

        # Lock sauber initialisieren
        try:
            context.scene[LOCK_KEY] = False
        except Exception:
            pass

        # Preflight-Helper (behalten – stellt Marker/Settings ein)
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
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        self._bootstrap(context)
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_every, window=context.window)
        context.window_manager.modal_handler_add(self)
        self._log("Start")
        return {"RUNNING_MODAL"}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        return self.invoke(context, None)

    # ------------------------------------------------------------
    # Modal FSM (Detect-Only)
    # ------------------------------------------------------------
    def modal(self, context: bpy.types.Context, event) -> Set[str]:
        # Detect-Lock respektieren
        try:
            if context.scene.get(LOCK_KEY, False):
                return {"RUNNING_MODAL"}
        except Exception:
            pass

        if event.type == "ESC":
            return self._cancel(context, "ESC gedrückt")

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if not context.area or context.area.type != "CLIP_EDITOR":
            return self._cancel(context, "CLIP_EDITOR-Kontext verloren")

        # --- FSM ---
        if self._state == "INIT":
            self._state = "FIND_LOW"
            return {"RUNNING_MODAL"}

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
                # Nichts zu tun → direkt Detect am aktuellen Frame testen
                context.scene["goto_frame"] = int(context.scene.frame_current)
                self._jump_done = False
                self._detect_attempts = 0
                self._state = "JUMP"
            else:
                # Fallback: aktueller Frame
                context.scene["goto_frame"] = int(context.scene.frame_current)
                self._jump_done = False
                self._detect_attempts = 0
                self._state = "JUMP"
            return {"RUNNING_MODAL"}

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
            # Nach Jump kurz warten, damit Depsgraph/Redraw stabil ist
            self._settle_ticks = max(0, int(self.settle_ticks_after_jump))
            self._state = "WAIT_GOTO" if self._settle_ticks > 0 else "PRE_DETECT"
            return {"RUNNING_MODAL"}

        elif self._state == "WAIT_GOTO":
            if self._settle_ticks > 0:
                self._settle_ticks -= 1
                try:
                    context.view_layer.update()
                except Exception:
                    pass
                try:
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                except Exception:
                    pass
                return {"RUNNING_MODAL"}
            self._state = "PRE_DETECT"
            return {"RUNNING_MODAL"}

        elif self._state == "PRE_DETECT":
            # Vor Detect: Strings bereinigen, um Encoding-Fails zu vermeiden
            _sanitize_all_track_names(context)
            self._state = "DETECT"
            return {"RUNNING_MODAL"}

        elif self._state == "DETECT":
            goto = int(context.scene.get("goto_frame", context.scene.frame_current))
            try:
                from ..Helper.detect import run_detect_once
                res = run_detect_once(context, start_frame=goto, handoff_to_pipeline=False)
            except UnicodeDecodeError as ex:
                self._log(f"[Detect] UnicodeDecodeError – Retry nach Sanitize: {ex}")
                _sanitize_all_track_names(context)
                try:
                    from ..Helper.detect import run_detect_once as _retry_detect
                    res = _retry_detect(context, start_frame=goto, handoff_to_pipeline=False)
                except Exception as ex2:
                    self._log(f"[Detect] Ausnahme (Retry): {ex2}")
                    res = {"status": "FAILED", "reason": f"exception(retry):{ex2}"}
            except Exception as ex:
                self._log(f"[Detect] Ausnahme: {ex}")
                res = {"status": "FAILED", "reason": f"exception:{ex}"}

            # Ergebnis an Szene hängen (zum Debuggen in der UI)
            try:
                context.scene["detect_last_result"] = dict(res)
            except Exception:
                pass

            st = res.get("status", "FAILED")
            if st == "READY":
                self._log("[Detect] READY – Test abgeschlossen.")
                return self._finish(context, cancelled=False)

            if st == "RUNNING":
                self._detect_attempts += 1
                if self._detect_attempts >= int(self.max_detect_attempts):
                    self._log("[Detect] Timebox erreicht – Test beendet (RUNNING).")
                    return self._finish(context, cancelled=False)
                # Andernfalls erneut TRY in nächstem Tick
                return {"RUNNING_MODAL"}

            # FAILED → Test sofort beenden (Fehler sichtbar lassen)
            self._log(f"[Detect] FAILED – {res.get('reason', '')}")
            return self._finish(context, cancelled=False)

        elif self._state == "DONE":
            return self._finish(context, cancelled=False)

        return {"RUNNING_MODAL"}
