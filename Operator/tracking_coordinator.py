from __future__ import annotations
"""
Tracking-Orchestrator – Schritt 3
---------------------------------
Fügt zum Schritt-2-Stand den State "DETECT" hinzu und bindet Helper/detect.py an.
Ablauf gem. Vorgabe (Kurzfassung):
  INIT → FIND_LOW → JUMP → DETECT → TRACK_FWD → TRACK_BWD? → CLEAN_SHORT → (Loop)

- FIND_LOW nutzt Helper/find_low_marker_frame.py
- JUMP nutzt Helper/jump_to_frame.py
- DETECT nutzt Helper/detect.py (run_detect_once)
- CLEAN_ERROR bleibt als Alternativzweig aus Schritt 2 erhalten

Hinweise:
- PEP 8-konform, UI-robust (CLIP_EDITOR-Check im poll)
- Globaler Detect-Lock scene["__detect_lock"] wird respektiert
- Timebox für wiederholte Detect-Versuche: 8
"""

import bpy
from typing import Optional, Dict, Any

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


# ------------------------------------------------------------
# Kleine Utilities / Konstanten
# ------------------------------------------------------------
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8


def _has_clip_editor(context: bpy.types.Context) -> bool:
    area = getattr(context, "area", None)
    return bool(area and getattr(area, "type", None) == "CLIP_EDITOR")


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


# ------------------------------------------------------------
# Orchestrator-Operator
# ------------------------------------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Pipeline)"
    bl_options = {"REGISTER", "UNDO"}

    # --- UI Properties ---
    use_apply_settings: bpy.props.BoolProperty(  # type: ignore[valid-type]
        name="Apply Tracker Defaults",
        description="Vor Start Standard-Tracking-Settings anwenden",
        default=True,
    )
    do_backward: bpy.props.BoolProperty(  # type: ignore[valid-type]
        name="Bidirectional",
        description="Marker nach vorne und hinten tracken",
        default=True,
    )
    auto_clean_short: bpy.props.BoolProperty(  # type: ignore[valid-type]
        name="Auto Clean Short",
        description="Kurztracks nach jedem Tracking-Pass bereinigen",
        default=True,
    )

    # --- interne Laufzeit-Variablen ---
    _timer: Optional[bpy.types.Timer] = None
    _state: str = "INIT"
    _detect_attempts: int = 0
    _jump_done: bool = False

    # Wiederholungszähler für Jump-Frames (für spätere Optimizer-Hooks)
    _repeat_map: Dict[int, int]

    # --------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------
    @classmethod
    def poll(cls, context):
        # Bootstrap darf nur im Clip-Editor gestartet werden (deine Vorgabe)
        return _has_clip_editor(context)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        # 1) Bootstrap
        self._bootstrap(context)

        # 2) Modal: Timer + Handler
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        _safe_report(self, {"INFO"}, "Coordinator gestartet (INIT)")
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        # ESC → sauberer Abbruch
        if event.type in {"ESC"}:
            return self._finish(context, cancelled=True)

        # Wir ticken nur auf Timer-Events
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # Safety: Wenn gerade Detect läuft, nichts tun
        try:
            if context.scene.get(_LOCK_KEY, False):
                return {"RUNNING_MODAL"}
        except Exception:
            pass

        # FSM schrittweise verarbeiten
        try:
            if self._state == "INIT":
                return self._state_init(context)
            elif self._state == "FIND_LOW":
                return self._state_find_low(context)
            elif self._state == "JUMP":
                return self._state_jump(context)
            elif self._state == "DETECT":
                return self._state_detect(context)
            elif self._state == "CLEAN_ERROR":
                return self._state_clean_error(context)
            elif self._state in {"TRACK_FWD", "TRACK_BWD", "CLEAN_SHORT", "SOLVE"}:
                # werden in späteren Schritten implementiert
                _safe_report(self, {"INFO"}, f"State '{self._state}' ist noch nicht implementiert – wechsle zu FINALIZE")
                self._state = "FINALIZE"
                return {"RUNNING_MODAL"}
            elif self._state == "FINALIZE":
                return self._finish(context, cancelled=False)
            else:
                _safe_report(self, {"WARNING"}, f"Unbekannter State '{self._state}' – Abbruch")
                return self._finish(context, cancelled=True)
        except Exception as ex:
            _safe_report(self, {"ERROR"}, f"Modal-Fehler: {ex}")
            return self._finish(context, cancelled=True)

    # --------------------------------------------------------
    # Bootstrap
    # --------------------------------------------------------
    def _bootstrap(self, context: bpy.types.Context) -> None:
        scn = context.scene

        # Globalen Lock zurücksetzen
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass

        # Marker-Helfer: robust importieren (Paket/Pfad egal)
        try:
            from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
        except Exception:
            marker_helper_main = None  # type: ignore

        if marker_helper_main is not None:
            try:
                ok, adapt, _ = marker_helper_main(context)
                _safe_report(self, {"INFO"}, f"Marker Helper gestartet (adapt={adapt})")
            except Exception as ex:
                _safe_report(self, {"WARNING"}, f"Marker Helper fehlgeschlagen: {ex}")
        else:
            _safe_report(self, {"WARNING"}, "Marker Helper nicht verfügbar")

        # Tracker Defaults (optional)
        if self.use_apply_settings:
            try:
                from ..Helper.tracker_settings import apply_tracker_settings  # type: ignore
                apply_tracker_settings(context, log=True)
                _safe_report(self, {"INFO"}, "Tracker Defaults gesetzt")
            except Exception as ex:
                _safe_report(self, {"WARNING"}, f"Tracker Settings fehlgeschlagen: {ex}")

        # FSM-Startwerte
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}

    # --------------------------------------------------------
    # States – INIT, FIND_LOW, JUMP, DETECT, CLEAN_ERROR
    # --------------------------------------------------------
    def _state_init(self, context: bpy.types.Context):
        # Direkt in die erste Suche übergehen
        self._state = "FIND_LOW"
        print("[FSM] INIT → FIND_LOW")
        return {"RUNNING_MODAL"}

    def _state_find_low(self, context: bpy.types.Context):
        """Ermittelt ersten Frame mit zu niedriger Markerdichte.
        Übergänge:
          FOUND  → setze goto_frame, state="JUMP"
          NONE   → state="SOLVE"  (alle Marker >= Basis)
          FAILED → wie FOUND behandeln (best effort)
        """
        # Import lokal halten (robust gegenüber Paket-Struktur)
        try:
            from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
        except Exception:
            try:
                from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
            except Exception as ex:
                _safe_report(self, {"ERROR"}, f"FindLow nicht verfügbar: {ex}")
                return self._finish(context, cancelled=True)

        try:
            result = run_find_low_marker_frame(context)
        except Exception as ex:
            _safe_report(self, {"WARNING"}, f"FindLow FAILED: {ex} – best effort JUMP")
            result = {"status": "FAILED"}

        status = str(result.get("status", "FAILED")).upper()
        if status == "FOUND":
            f = int(result.get("frame", context.scene.frame_current))
            context.scene[_GOTO_KEY] = f
            self._jump_done = False
            self._detect_attempts = 0
            self._state = "JUMP"
            print(f"[FSM] FIND_LOW → JUMP (goto={f})")
        elif status == "NONE":
            self._state = "SOLVE"
            print("[FSM] FIND_LOW → SOLVE (keine Low-Frames)")
        else:  # FAILED → best effort → JUMP
            context.scene[_GOTO_KEY] = int(context.scene.frame_current)
            self._jump_done = False
            self._detect_attempts = 0
            self._state = "JUMP"
            print("[FSM] FIND_LOW FAILED → JUMP (best effort)")
        return {"RUNNING_MODAL"}

    def _state_jump(self, context: bpy.types.Context):
        try:
            from ..Helper.jump_to_frame import run_jump_to_frame  # type: ignore
        except Exception as ex:
            _safe_report(self, {"ERROR"}, f"Jump nicht verfügbar: {ex}")
            return self._finish(context, cancelled=True)

        goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
        try:
            res = run_jump_to_frame(context, frame=goto, repeat_map=self._repeat_map)
        except Exception as ex:
            _safe_report(self, {"WARNING"}, f"Jump-Fehler: {ex}")
            res = {"status": "FAILED"}

        if str(res.get("status", "FAILED")).upper() != "OK":
            # Trotz Fehler weiter – DETECT versuchen
            print("[FSM] JUMP result != OK – trotzdem weiter zu DETECT")
        else:
            self._jump_done = True

        self._state = "DETECT"
        print("[FSM] JUMP → DETECT")
        return {"RUNNING_MODAL"}

    def _state_detect(self, context: bpy.types.Context):
        """Führt eine einzelne Marker-Detektion durch und entscheidet über die nächsten Schritte."""
        try:
            from ..Helper.detect import run_detect_once  # type: ignore
        except Exception as ex:
            _safe_report(self, {"ERROR"}, f"Detect nicht verfügbar: {ex}")
            return self._finish(context, cancelled=True)

        goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
        result: Dict[str, Any]
        try:
            result = run_detect_once(context, start_frame=goto, handoff_to_pipeline=True)
        except Exception as ex:
            _safe_report(self, {"ERROR"}, f"Detect-Fehler: {ex}")
            result = {"status": "FAILED"}

        status = str(result.get("status", "FAILED")).upper()
        print(f"[FSM] DETECT → Ergebnis {status} (Versuch {self._detect_attempts})")

        if status == "READY":
            self._detect_attempts = 0
            self._state = "TRACK_FWD"
        elif status == "RUNNING":
            self._detect_attempts += 1
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                _safe_report(self, {"WARNING"}, "Detect Timebox erreicht – weiter mit TRACK_FWD")
                self._detect_attempts = 0
                self._state = "TRACK_FWD"
            else:
                # im selben State bleiben → nächster Timer-Tick versucht erneut
                self._state = "DETECT"
        else:  # FAILED oder unbekannt
            self._detect_attempts = 0
            self._state = "TRACK_FWD"

        return {"RUNNING_MODAL"}

    def _state_clean_error(self, context: bpy.types.Context):
        try:
            from ..Helper.clean_error_tracks import run_clean_error_tracks  # type: ignore
        except Exception as ex:
            _safe_report(self, {"ERROR"}, f"CleanError nicht verfügbar: {ex}")
            return self._finish(context, cancelled=True)

        try:
            run_clean_error_tracks(context, show_popups=False)
        except Exception as ex:
            _safe_report(self, {"WARNING"}, f"CleanError-Fehler: {ex}")

        # Nach CLEAN_ERROR aktuell in FINALIZE übergehen
        self._state = "FINALIZE"
        print("[FSM] CLEAN_ERROR → FINALIZE")
        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Finalize / Cleanup
    # --------------------------------------------------------
    def _finish(self, context: bpy.types.Context, *, cancelled: bool):
        # Timer entfernen, Lock freigeben
        try:
            if self._timer is not None:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        try:
            context.scene[_LOCK_KEY] = False
        except Exception:
            pass
        return {"CANCELLED"} if cancelled else {"FINISHED"}


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
