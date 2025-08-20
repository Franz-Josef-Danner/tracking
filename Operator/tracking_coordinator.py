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
"""

import bpy
from typing import Optional, Dict

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

# Scene Keys
_LOCK_KEY = "__detect_lock"
_GOTO_KEY = "goto_frame"
_MAX_DETECT_ATTEMPTS = 8

_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"
_CLEAN_SKIP_ONCE = "__skip_clean_short_once"  # vom Cleaner respektiert

# --- Neu: Keys für Optimizer-Signal (werden von Helper/jump_to_frame.py gesetzt) ---
_OPT_REQ_KEY = "__optimize_request"
_OPT_REQ_VAL = "JUMP_REPEAT"
_OPT_FRAME_KEY = "__optimize_frame"


def _safe_report(self: bpy.types.Operator, level: set, msg: str) -> None:
    try:
        self.report(level, msg)
    except Exception:
        print(f"[Coordinator] {msg}")


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

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    # ---------------- Lifecycle ----------------

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
        elif self._state == "SOLVE":                     # ← NEU
            return self._state_solve(context) 
        elif self._state == "FINALIZE":
            return self._finish(context, cancelled=False)

        return self._finish(context, cancelled=True)

    # ---------------- Bootstrap ----------------

    def _bootstrap(self, context):
        scn = context.scene
        scn[_LOCK_KEY] = False
        scn[_BIDI_ACTIVE_KEY] = False
        scn[_BIDI_RESULT_KEY] = ""
        self._state = "INIT"
        self._detect_attempts = 0
        self._jump_done = False
        self._repeat_map = {}
        self._bidi_started = False

    # ---------------- States ----------------

    def _state_init(self, context):
        print("[Coord] INIT → FIND_LOW")
        self._state = "FIND_LOW"
        return {"RUNNING_MODAL"}

    def _state_find_low(self, context):
        from ..Helper.find_low_marker_frame import run_find_low_marker_frame  # type: ignore
        from ..Helper.clean_error_tracks import run_clean_error_tracks        # type: ignore  # 

        result = run_find_low_marker_frame(context)
        status = str(result.get("status", "FAILED")).upper()

        if status == "FOUND":
            frame = int(result.get("frame", context.scene.frame_current))
            context.scene[_GOTO_KEY] = frame
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FOUND frame={frame} → JUMP")
            self._state = "JUMP"

        elif status == "NONE":
            # Erweiterung: Error‑Cleanup fahren und anhand des Feedbacks verzweigen
            print("[Coord] FIND_LOW → NONE → run_clean_error_tracks()")
            try:
                cr = run_clean_error_tracks(context, show_popups=False)  # {'FINISHED'} | {'CANCELLED'} | evtl. dict
            except Exception as ex:
                print(f"[Coord] CLEAN_ERROR_TRACKS Exception: {ex!r} → CANCEL")
                return self._finish(context, cancelled=True)

            def _map_clean_result(r) -> str:
                # set-artige Rückgaben {'FINISHED'} / {'CANCELLED'}
                if isinstance(r, set):
                    return "OK" if "FINISHED" in r else "FAILED"
                # dict-Rückgaben (robust)
                if isinstance(r, dict):
                    st = str(r.get("status", "")).upper()
                    if st in {"OK", "NONE", "FAILED"}:
                        return st
                    if st == "CANCELLED":
                        return "FAILED"
                    deleted = r.get("deleted", None)
                    if isinstance(deleted, int):
                        return "OK" if deleted > 0 else "NONE"
                # Fallback konservativ: erneut suchen
                return "OK"

            mapped = _map_clean_result(cr)
            print(f"[Coord] CLEAN_ERROR_TRACKS → mapped={mapped}")

            if mapped == "OK":
                # Es wurden Marker/Tracks bereinigt → Loop fortsetzen und erneut Low‑Frames suchen
                self._state = "FIND_LOW"
            elif mapped == "NONE":
                # Keine Änderungen → Solve starten
                self._state = "SOLVE"
            else:  # "FAILED"
                _safe_report(self, {"ERROR"}, "Clean Error Tracks fehlgeschlagen – Abbruch.")
                return self._finish(context, cancelled=True)

        else:
            # Best effort: versuche mit aktuellem Frame weiter
            context.scene[_GOTO_KEY] = context.scene.frame_current
            self._jump_done = False
            print(f"[Coord] FIND_LOW → FAILED ({result.get('reason', '?')}) → JUMP (best-effort)")
            self._state = "JUMP"

        return {"RUNNING_MODAL"}

    def _state_solve(self, context):
        """Solve‑Phase nach NONE→CleanErrorTracks(NONE)."""
        try:
            from ..Helper.solve_camera import solve_watch_clean  # type: ignore  # 
            print("[Coord] SOLVE → solve_watch_clean()")
            solve_watch_clean(context)
        except Exception as ex:
            print(f"[Coord] SOLVE failed: {ex!r}")
            return self._finish(context, cancelled=True)
        print("[Coord] SOLVE → FINALIZE")
        self._state = "FINALIZE"
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

            # ---------------------- NEU: Optimizer-Signal verwerten ----------------------
            scn = context.scene
            opt_req = scn.get(_OPT_REQ_KEY, None)
            # Herkunftsframe aus Scene übernehmen oder auf den gesprungenen Frame zurückfallen
            opt_frame = int(scn.get(_OPT_FRAME_KEY, jr.get('frame', scn.frame_current)))
            if jr.get("optimize_signal") or opt_req == _OPT_REQ_VAL:
                # Signal verbrauchen
                scn.pop(_OPT_REQ_KEY, None)
                # Frame-Info belassen; Helper/Optimizer kann _OPT_FRAME_KEY auslesen
                scn[_OPT_FRAME_KEY] = opt_frame
                try:
                    # Bevorzugt: direkte Startfunktion, falls Helper dies anbietet
                    try:
                        from ..Helper.optimize_tracking_modal import start_optimization  # type: ignore
                        start_optimization(context, origin_frame=opt_frame)
                        print(f"[Coord] JUMP → OPTIMIZE (start_optimization, frame={opt_frame})")
                    except Exception:
                        # Fallback: Operator-Start (falls als Operator registriert)
                        bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
                        print(f"[Coord] JUMP → OPTIMIZE (operator invoke, frame={opt_frame})")
                except Exception as ex:
                    print(f"[Coord] OPTIMIZE launch failed: {ex!r}")
            # ---------------------------------------------------------------------------

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
            handoff_to_pipeline=True,  # wichtig: Signal "success" setzen (für Tools/Debug, Koordinator erzwingt TRACK)
        )
        status = str(res.get("status", "FAILED")).upper()

        if status == "RUNNING":
            self._detect_attempts += 1
            print(f"[Coord] DETECT → RUNNING (attempt {self._detect_attempts}/{_MAX_DETECT_ATTEMPTS})")
            if self._detect_attempts >= _MAX_DETECT_ATTEMPTS:
                print("[Coord] DETECT Timebox erreicht → force TRACK")
                # Einmaliger Clean-Skip als Airbag, falls jemand extern säubern will
                context.scene[_CLEAN_SKIP_ONCE] = True
                self._state = "TRACK"
            return {"RUNNING_MODAL"}

        # READY oder FAILED: weiter zu Bi-Track (kein anderer Pfad)
        self._detect_attempts = 0
        context.scene[_CLEAN_SKIP_ONCE] = True  # Airbag: CleanShort erst NACH Bi-Track
        print(f"[Coord] DETECT → {status} → TRACK (Bidirectional)")
        self._state = "TRACK"
        return {"RUNNING_MODAL"}

    def _state_track(self, context):
        """Startet und überwacht den Bidirectional-Operator. CleanShort kommt erst nach Abschluss."""
        scn = context.scene

        if not self._bidi_started:
            # sicherstellen, dass Flags sauber sind
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

        # warten bis Operator „aktiv“ meldet bzw. fertig ist
        if scn.get(_BIDI_ACTIVE_KEY, False):
            # noch beschäftigt
            print("[Coord] TRACK → waiting (bidi_active=True)")
            return {"RUNNING_MODAL"}

        # Operator hat beendet → Ergebnis prüfen (nur Logging)
        result = str(scn.get(_BIDI_RESULT_KEY, "") or "").upper()
        scn[_BIDI_RESULT_KEY] = ""
        self._bidi_started = False
        print(f"[Coord] TRACK → finished (result={result or 'NONE'}) → CLEAN_SHORT")
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
                    respect_fresh=True,
                    verbose=True,
                )
            except Exception as ex:
                print(f"[Coord] CLEAN_SHORT failed: {ex!r}")

        # in die nächste Runde
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
