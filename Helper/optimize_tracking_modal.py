from __future__ import annotations
import bpy
from bpy.types import Operator
from typing import Optional, Dict, Any

# -----------------------------------------------------------------------------
# Externe Helper (nur Funktionen, keine Operatoren direkt aus diesem Modul)
# -----------------------------------------------------------------------------
try:
    # Detect: einzelner Pass, liefert Status {status: RUNNING|READY|FAILED, frame, ...}
    from .detect import run_detect_once  # type: ignore
except Exception:  # pragma: no cover
    run_detect_once = None  # type: ignore

try:
    # Tracking: vorwärts, INVOKE_DEFAULT, sequence=True, Playhead-Reset per Timer
    from .tracking_helper import track_to_scene_end_fn  # type: ignore
except Exception:  # pragma: no cover
    track_to_scene_end_fn = None  # type: ignore

__all__ = ["CLIP_OT_optimize_tracking_modal"]


class CLIP_OT_optimize_tracking_modal(Operator):
    """
    Optimierungs-Flow ohne direkte Operator-Aufrufe:
      1) Detect per Helper.detect.run_detect_once (ggf. mehrfach bis READY)
      2) Tracking vorwärts per Helper.tracking_helper.track_to_scene_end_fn
      3) Warten auf Fertig-Signal (Token), dann Abschluss

    Regeln (vom Nutzer):
      • Regel 1: Kein Operator hier; nur Helper-Funktionen verwenden.
      • Regel 2: Nur vorwärts tracken.
      • Regel 3: 'INVOKE_DEFAULT', backwards=False, sequence=True (in tracking_helper implementiert).
      • Regel 4: Playhead nach dem Tracken zurück auf Ursprungs-Frame (tracking_helper garantiert dies + extra Check).
    """

    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimiertes Tracking (Modal)"
    bl_options = {"REGISTER", "UNDO"}

    # ------------------ interne Zustände ------------------
    _timer: Optional[bpy.types.Timer] = None
    _state: str = "INIT"
    _origin_frame: int = 0
    _detect_attempts: int = 0
    _detect_max_attempts: int = 8
    _last_detect: Dict[str, Any] | None = None
    _coord_token: str = ""

    # ------------------ Operator Lifecycle ------------------
    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        # Sanity: Helper vorhanden?
        if run_detect_once is None:
            self.report({'ERROR'}, "Helper.detect.run_detect_once nicht verfügbar.")
            return {'CANCELLED'}
        if track_to_scene_end_fn is None:
            self.report({'ERROR'}, "Helper.tracking_helper.track_to_scene_end_fn nicht verfügbar.")
            return {'CANCELLED'}

        # Ausgangsframe merken
        self._origin_frame = int(context.scene.frame_current)
        self._state = "DETECT"
        self._detect_attempts = 0
        self._last_detect = None
        self._coord_token = f"bw_optimize_token_{id(self)}"

        wm = context.window_manager
        win = getattr(context, "window", None) or getattr(bpy.context, "window", None)
        if not win:
            self.report({'ERROR'}, "Kein aktives Window – TIMER kann nicht registriert werden.")
            return {'CANCELLED'}

        # alten Timer entfernen
        try:
            if self._timer:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass

        # Timer registrieren (sanft)
        self._timer = wm.event_timer_add(0.2, window=win)
        wm.modal_handler_add(self)
        print("[Optimize] Start → state=DETECT, origin=", self._origin_frame)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None

    # ------------------ Modal-Loop ------------------
    def modal(self, context, event):
        try:
            if event.type == 'ESC':
                self.report({'WARNING'}, "Optimierung abgebrochen (ESC).")
                self.cancel(context)
                return {'CANCELLED'}

            if event.type != 'TIMER':
                return {'PASS_THROUGH'}

            # Kontext-Validierung (Clip-Editor erforderlich?) – optional
            space = getattr(context, 'space_data', None)
            if not space or getattr(space, 'type', '') != 'CLIP_EDITOR':
                # Nicht hart abbrechen, aber warnen
                print("[Optimize] WARN: Kein CLIP_EDITOR fokussiert – fahre trotzdem fort.")

            # FSM-Step
            if self._state == "DETECT":
                return self._step_detect(context)
            elif self._state == "TRACK_START":
                return self._step_track_start(context)
            elif self._state == "TRACK_WAIT":
                return self._step_track_wait(context)
            elif self._state == "FINISH":
                self.cancel(context)
                return {'FINISHED'}
            else:
                # Unbekannter Zustand → sauber beenden
                self.report({'ERROR'}, f"Unbekannter Zustand: {self._state}")
                self.cancel(context)
                return {'CANCELLED'}
        except Exception as ex:  # noqa: BLE001
            self.report({'ERROR'}, f"Modal crashed: {ex}")
            self.cancel(context)
            return {'CANCELLED'}

    # ------------------ Zustands-Implementierungen ------------------
    def _step_detect(self, context):
        """Führt einzelne Detect-Pässe aus, bis READY/FAILED gemeldet wird."""
        scn = context.scene
        # Safety: nicht parallel, falls ein Lock aus anderem Code aktiv wäre
        if bool(scn.get("__detect_lock", False)):
            # Warten bis Detect frei ist
            return {'RUNNING_MODAL'}

        # Detect-Pass
        self._detect_attempts += 1
        print(f"[Optimize][Detect] attempt {self._detect_attempts}/{self._detect_max_attempts} @frame={self._origin_frame}")
        try:
            res = run_detect_once(
                context,
                start_frame=int(self._origin_frame),
                handoff_to_pipeline=False,
            )
        except Exception as ex:  # noqa: BLE001
            self.report({'ERROR'}, f"Detect-Helper Exception: {ex}")
            return {'CANCELLED'}

        self._last_detect = dict(res or {})
        status = str(self._last_detect.get('status', 'FAILED'))
        print(f"[Optimize][Detect] status={status} → data={self._last_detect}")

        if status == 'RUNNING' and self._detect_attempts < self._detect_max_attempts:
            # weiterer Versuch im nächsten Timer-Tick
            return {'RUNNING_MODAL'}

        if status == 'READY' or (status == 'RUNNING' and self._detect_attempts >= self._detect_max_attempts):
            # Weiter zum Tracking
            self._state = "TRACK_START"
            return {'RUNNING_MODAL'}

        # FAILED → trotzdem versuchen zu tracken (best effort)
        self._state = "TRACK_START"
        return {'RUNNING_MODAL'}

    def _step_track_start(self, context):
        """Startet das Vorwärts-Tracking via Helper und initialisiert das Feedback-Token."""
        wm = context.window_manager
        # Token vorab bereinigen
        try:
            if wm.get("bw_tracking_done_token", None) == self._coord_token:
                del wm["bw_tracking_done_token"]
        except Exception:
            pass

        # Tracking starten (nicht blockierend; Helper registriert Timer & setzt Token bei Fertig)
        print(f"[Optimize][Track] start forward tracking (token={self._coord_token})")
        try:
            track_to_scene_end_fn(
                context,
                coord_token=self._coord_token,
                start_frame=int(self._origin_frame),
                debug=True,
                first_delay=0.25,
            )
        except Exception as ex:  # noqa: BLE001
            self.report({'ERROR'}, f"Tracking-Helper Exception: {ex}")
            return {'CANCELLED'}

        self._state = "TRACK_WAIT"
        return {'RUNNING_MODAL'}

    def _step_track_wait(self, context):
        """Wartet, bis tracking_helper das Fertig-Token setzt; prüft zusätzlich Playhead-Reset."""
        wm = context.window_manager
        token = wm.get("bw_tracking_done_token", None)
        if token != self._coord_token:
            # noch nicht fertig
            return {'RUNNING_MODAL'}

        # Fertig – Token aufräumen
        try:
            del wm["bw_tracking_done_token"]
        except Exception:
            pass

        # Regel 4: Playhead-Reset sicherstellen (Scene + Editoren)
        # tracking_helper erledigt das bereits, aber wir prüfen hart und korrigieren ggf.
        cur = int(context.scene.frame_current)
        if cur != int(self._origin_frame):
            print(f"[Optimize][Track] WARN: scene.frame_current={cur} != origin={self._origin_frame} → set")
            try:
                context.scene.frame_set(int(self._origin_frame))
            except Exception:
                context.scene.frame_current = int(self._origin_frame)

        # Abschluss
        self._state = "FINISH"
        print("[Optimize] FINISH")
        return {'RUNNING_MODAL'}


# Optional: Register/Unregister – falls das Modul eigenständig getestet wird
def register():  # pragma: no cover
    bpy.utils.register_class(CLIP_OT_optimize_tracking_modal)

def unregister():  # pragma: no cover
    bpy.utils.unregister_class(CLIP_OT_optimize_tracking_modal)
