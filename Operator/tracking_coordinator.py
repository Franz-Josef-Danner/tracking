from __future__ import annotations
"""
Tracking-Orchestrator – Schritt 1
---------------------------------
Bootstrap + Modal/FSM-Skelett mit den ersten Zuständen "INIT" → "FIND_LOW".

In diesem Schritt:
- Operator startet modal mit Timer.
- Bootstrap setzt Hilfswerte und (optional) Tracker-Defaults.
- FSM führt ersten Übergang INIT → FIND_LOW aus.
- FIND_LOW ruft run_find_low_marker_frame() auf und entscheidet über nächste States:
    - FOUND  → goto_frame setzen, wechselt zu "JUMP"
    - NONE   → wechselt zu "SOLVE" (Ablauf fertig vorbereitet)
    - FAILED → best effort: wie FOUND behandeln, wenn möglich

Weitere States (JUMP, DETECT, TRACK_FWD, TRACK_BWD, CLEAN_SHORT, SOLVE, FINALIZE)
werden in den nächsten Schritten implementiert.

Hinweis: Dieser Operator ist PEP 8-konform, robust gegen fehlende UI-Kontexte
und loggt klar nachvollziehbare Schritte.
"""

import bpy
from typing import Optional, Dict, Any

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


# ------------------------------------------------------------
# Kleine Utilities / Konstanten
# ------------------------------------------------------------
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"


def _has_clip_editor(context: bpy.types.Context) -> bool:
    area = getattr(context, "area", None)
    return bool(area and getattr(area, "type", None) == "CLIP_EDITOR")


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


# ------------------------------------------------------------
# Orchestrator-Operator (Schritt 1)
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
        # Bootstrap darf nur im Clip-Editor gestartet werden (dein Wunsch)
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
            elif self._state in {"JUMP", "DETECT", "TRACK_FWD", "TRACK_BWD", "CLEAN_SHORT", "SOLVE"}:
                # werden in späteren Schritten implementiert
                _safe_report(self, {"INFO"}, f"State '{self._state}' ist noch nicht implementiert – wechsle zu FINALIZE")
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
    # States – Schritt 1: INIT, FIND_LOW
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
          NONE   → state="SOLVE"
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

        result: Dict[str, Any] = run_find_low_marker_frame(
            context,
            prefer_adapt=True,
            use_scene_basis=True,
            frame_start=None,
            frame_end=None,
        )

        status = str(result.get("status", "FAILED")).upper()
        frame = result.get("frame", None)
        print(f"[FIND_LOW] status={status} frame={frame}")

        scn = context.scene
        if status == "FOUND" and isinstance(frame, int):
            scn[_GOTO_KEY] = int(frame)
            self._jump_done = False
            self._detect_attempts = 0
            self._state = "JUMP"  # Implementierung folgt in Schritt 2
            _safe_report(self, {"INFO"}, f"Low-Marker bei Frame {frame} → JUMP")
            return {"RUNNING_MODAL"}

        if status == "NONE":
            self._state = "SOLVE"  # Implementierung folgt in späterem Schritt
            _safe_report(self, {"INFO"}, "Keine Low-Marker-Frames → SOLVE")
            return {"RUNNING_MODAL"}

        # FAILED → Best-Effort: Wenn wir irgendeinen Frame vorschlagen können, tun wir es
        if isinstance(frame, int):
            scn[_GOTO_KEY] = int(frame)
            self._jump_done = False
            self._detect_attempts = 0
            self._state = "JUMP"
            _safe_report(self, {"WARNING"}, f"FindLow FAILED – nutze Frame {frame} → JUMP")
            return {"RUNNING_MODAL"}

        _safe_report(self, {"ERROR"}, "FindLow FAILED ohne Frame – Abbruch")
        return self._finish(context, cancelled=True)

    # --------------------------------------------------------
    # Abschluss/Cleanup
    # --------------------------------------------------------
    def _finish(self, context: bpy.types.Context, *, cancelled: bool) -> set:
        # Timer aufräumen
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

        # Lock freigeben
        try:
            context.scene[_LOCK_KEY] = False
        except Exception:
            pass

        msg = "Abgebrochen" if cancelled else "Fertig"
        _safe_report(self, {"INFO"}, f"Coordinator: {msg}")
        return {"CANCELLED"} if cancelled else {"FINISHED"}


# ------------------------------------------------------------
# Registrierung
# ------------------------------------------------------------
def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
