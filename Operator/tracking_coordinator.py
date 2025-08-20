from __future__ import annotations
"""
Tracking-Orchestrator – Schritt 3/4
-----------------------------------
Vollständige FSM inkl. DETECT → TRACK_FWD → (optional) TRACK_BWD (via Bidi-Operator)
→ CLEAN_SHORT → Loop zurück zu FIND_LOW. Kompatibel zu den Helpern aus Helper/.*

Ablauf (Kurzfassung gemäß Vorgabe):
  INIT → FIND_LOW → JUMP → DETECT → TRACK_FWD → TRACK_BWD? → CLEAN_SHORT → (Loop)

Hinweise:
- PEP 8-konform, UI-robust (CLIP_EDITOR-Check im poll)
- Globaler Detect-Lock scene["__detect_lock"] wird respektiert
- Timebox für wiederholte Detect-Versuche: 8
- Bidirektionales Tracking über Operator "clip.bidirectional_track" mit Polling
- Short-Track-Cleanup über Helper.clean_short_tracks
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

# Bidirectional-Operator Flags
_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"


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
    _repeat_map: Dict[int, int]

    _bidi_started: bool = False

    # --------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------
    @classmethod
    def poll(cls, context):
        # Bootstrap darf nur im Clip-Editor gestartet werden
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
            elif self._state == "TRACK_FWD":
                return self._state_track_fwd(context)
            elif self._state == "TRACK_BWD":
                return self._state_track_bwd(context)
            elif self._state == "CLEAN_SHORT":
                return self._state_clean_short(context)
            elif self._state == "CLEAN_ERROR":
                return self._state_clean_error(context)
            elif self._state in {"SOLVE"}:
                return self._state_solve(context)
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

        # Bidi-Flags sauber initialisieren
        try:
            scn[_BIDI_ACTIVE_KEY] = False
            scn[_BIDI_RESULT_KEY] = ""
        except Exception:
            pass

        # FSM-Startwerte
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False

    # --------------------------------------------------------
    # States – INIT, FIND_LOW, JUMP, DETECT, TRACK_FWD/BWD, CLEAN_SHORT
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
        try:
            from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
        except Exception:
            try:
                from .Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
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
        except Exception:
            try:
                from .Helper.jump_to_frame import run_jump_to_frame  # type: ignore
            except Exception as ex:
                _safe_report(self, {"ERROR"}, f"Jump nicht verfügbar: {ex}")
                return self._finish(context, cancelled=True)

        if not self._jump_done or int(context.scene.frame_current) != int(context.scene.get(_GOTO_KEY, context.scene.frame_current)):
            res = run_jump_to_frame(
                context,
                frame=int(context.scene.get(_GOTO_KEY, context.scene.frame_current)),
                ensure_clip=True,
                ensure_tracking_mode=True,
                use_ui_override=True,
                repeat_map=self._repeat_map,
            )
            if str(res.get("status", "FAILED")).upper() != "OK":
                _safe_report(self, {"WARNING"}, f"Jump FAILED: {res}")
            self._jump_done = True
            print(f"[FSM] JUMP → frame={res.get('frame')} (repeat={res.get('repeat_count', 1)})")

        # Weiter zur Detektion
        self._state = "DETECT"
        return {"RUNNING_MODAL"}

    def _state_detect(self, context: bpy.types.Context):
        try:
            from ..Helper.detect import run_detect_once  # type: ignore
        except Exception:
            try:
                from .Helper.detect import run_detect_once  # type: ignore
            except Exception as ex:
                _safe_report(self, {"ERROR"}, f"Detect nicht verfügbar: {ex}")
                return self._finish(context, cancelled=True)

        goto = int(context.scene.get(_GOTO_KEY, context.scene.frame_current))
        try:
            result = run_detect_once(context, start_frame=goto)
        except Exception as ex:
            _safe_report(self, {"WARNING"}, f"Detect FAILED (Exception): {ex}")
            result = {"status": "FAILED"}

        status = str(result.get("status", "FAILED")).upper()
        if status == "READY":
            self._detect_attempts = 0
            self._state = "TRACK_FWD"
            print("[FSM] DETECT READY → TRACK_FWD")
        elif status == "RUNNING":
            self._detect_attempts += 1
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[FSM] DETECT Timebox erreicht → TRACK_FWD")
                self._detect_attempts = 0
                self._state = "TRACK_FWD"
            else:
                # im selben State bleiben → nächster Timer-Tick wieder DETECT
                print(f"[FSM] DETECT RUNNING (attempt {self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
        else:  # FAILED
            self._detect_attempts = 0
            self._state = "TRACK_FWD"
            print("[FSM] DETECT FAILED → TRACK_FWD")
        return {"RUNNING_MODAL"}

    def _state_track_fwd(self, context: bpy.types.Context):
        """Vorwärts-Tracking; danach je nach Option Bidi oder CleanShort."""
        try:
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
        except Exception as ex:
            _safe_report(self, {"WARNING"}, f"TrackFwd Fehler: {ex}")

        if bool(self.do_backward):
            self._state = "TRACK_BWD"
            self._bidi_started = False
            print("[FSM] TRACK_FWD → TRACK_BWD")
        else:
            self._state = "CLEAN_SHORT"
            print("[FSM] TRACK_FWD → CLEAN_SHORT")
        return {"RUNNING_MODAL"}

    def _state_track_bwd(self, context: bpy.types.Context):
        """Bidirektionales Tracking über separaten Operator mit Polling."""
        scn = context.scene

        # 1) Falls noch nicht gestartet: Operator triggern
        if not self._bidi_started:
            try:
                bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                self._bidi_started = True
                print("[FSM] TRACK_BWD: Bidirectional-Operator gestartet")
            except Exception as ex:
                _safe_report(self, {"WARNING"}, f"Bidi-Start fehlgeschlagen: {ex}")
                self._state = "CLEAN_SHORT"
                return {"RUNNING_MODAL"}

        # 2) Lauf überwachen (Flags werden vom Operator gesetzt/gelöscht)
        try:
            if scn.get(_BIDI_ACTIVE_KEY, False):
                return {"RUNNING_MODAL"}
        except Exception:
            pass

        # 3) Ergebnis prüfen
        result = str(scn.get(_BIDI_RESULT_KEY, "") or "").upper()
        if result not in {"FINISHED", "FAILED"}:
            result = "FINISHED"  # robustes Default
        print(f"[FSM] TRACK_BWD: Bidi-Result = {result}")

        # Cleanup der Flags für den nächsten Zyklus
        try:
            scn[_BIDI_ACTIVE_KEY] = False
            scn[_BIDI_RESULT_KEY] = ""
        except Exception:
            pass

        # Weiter zum Short-Clean
        self._state = "CLEAN_SHORT"
        print("[FSM] TRACK_BWD → CLEAN_SHORT")
        return {"RUNNING_MODAL"}

    def _state_clean_short(self, context: bpy.types.Context):
        """Kurz-Track-Bereinigung, dann zurück zu FIND_LOW (Loop)."""
        if bool(self.auto_clean_short):
            try:
                try:
                    from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore
                except Exception:
                    from .Helper.clean_short_tracks import clean_short_tracks  # type: ignore
                frames = int(getattr(context.scene, "frames_track", 25) or 25)
                checked, changed = clean_short_tracks(
                    context,
                    min_len=frames,
                    action="DELETE_TRACK",
                    respect_fresh=True,
                    verbose=True,
                )
                _safe_report(self, {"INFO"}, f"CleanShort: geprüft={checked}, geändert={changed}")
            except Exception as ex:
                _safe_report(self, {"WARNING"}, f"CleanShort Fehler: {ex}")
        else:
            print("[FSM] CLEAN_SHORT: übersprungen (auto_clean_short=False)")

        # Loop zurück zum Start der Analyse
        self._state = "FIND_LOW"
        print("[FSM] CLEAN_SHORT → FIND_LOW")
        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Optional: CLEAN_ERROR & SOLVE Platzhalter (für spätere Schritte)
    # --------------------------------------------------------
    def _state_clean_error(self, context: bpy.types.Context):
        _safe_report(self, {"INFO"}, "State 'CLEAN_ERROR' ist noch nicht implementiert – wechsle zu FINALIZE")
        self._state = "FINALIZE"
        return {"RUNNING_MODAL"}

    def _state_solve(self, context: bpy.types.Context):
        """Platzhalter für Solve-Pass; hier später erweitern (Refine, Projection-Cleanup, etc.)."""
        try:
            bpy.ops.clip.solve_camera()
            _safe_report(self, {"INFO"}, "Solve ausgeführt")
        except Exception as ex:
            _safe_report(self, {"WARNING"}, f"Solve Fehler: {ex}")
        self._state = "FINALIZE"
        print("[FSM] SOLVE → FINALIZE")
        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Finish / Cleanup
    # --------------------------------------------------------
    def _finish(self, context: bpy.types.Context, *, cancelled: bool) -> set:
        # Timer entfernen
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

        # Locks zurücksetzen (Safety)
        try:
            context.scene[_LOCK_KEY] = False
        except Exception:
            pass

        msg = "Coordinator abgebrochen" if cancelled else "Coordinator fertig"
        _safe_report(self, {"INFO"}, msg)
        return {"CANCELLED" if cancelled else "FINISHED"}


# ------------------------------------------------------------
# Register
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
