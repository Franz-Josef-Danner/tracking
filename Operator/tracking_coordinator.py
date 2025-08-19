from __future__ import annotations
import bpy
from bpy.types import Operator
from typing import Optional, Dict, Any, List

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
    # Erwartet: track_to_scene_end_fn(context, coord_token, start_frame, debug, first_delay)
    from .tracking_helper import track_to_scene_end_fn  # type: ignore
except Exception:  # pragma: no cover
    track_to_scene_end_fn = None  # type: ignore

try:
    # Fehler-Metrik; wir benutzen sie pro-Track via temporärer Selektion
    from .error_value import error_value  # type: ignore
except Exception:  # pragma: no cover
    error_value = None  # type: ignore

__all__ = ["CLIP_OT_optimize_tracking_modal"]


class CLIP_OT_optimize_tracking_modal(Operator):
    """
    Optimierungs-Flow (modal) gemäß Anforderungsliste.

    Kernideen:
      • Keine direkten Operator-Aufrufe hier (nur Helper-Funktionen verwenden).
      • Nur vorwärts tracken (tracking_helper erledigt intern INVOKE_DEFAULT, backwards=False, sequence=True).
      • Playhead nach dem Tracken zurück auf Ursprungs-Frame (Helper + zusätzlicher Check hier).

    Algorithmus (vereinfacht):
      pt/sus setzen → Detect → Track → scor(en): f_i/e_i summieren (ega)
      ev initialisieren; Korridor dg herunterzählen; bei Erfolg ev/ptv updaten;
      falls Korridor endet, Motion-Model-Schleife (mo 0..4) + Farbkanal-Kombi-Schleife (vv 0..4).
    """

    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimiertes Tracking (Modal)"
    bl_options = {"REGISTER", "UNDO"}

    # ------------------ interne Zustände ------------------
    _timer: Optional[bpy.types.Timer] = None
    _state: str = "INIT"  # INIT → DETECT_TRACK → SCORE → EVAL → ... → FINISH
    _origin_frame: int = 0

    # Such-/Scoringspeicher
    _ev: float = -1.0  # bestes EGA bisher
    _ega: float = 0.0
    _dg: int = 4       # Korridor-Zähler
    _pt: int = 21      # Pattern Size
    _sus: int = 42     # Search Size
    _ptv: int = 21     # gemerkte Pattern Size (best)

    _mo_index: int = 0  # 0..4
    _mov_best: int = 0
    _vv: int = 0        # 0..4 (Kanal-Kombi)
    _vf_best: int = 0

    # Detect/Track Feedback
    _detect_attempts: int = 0
    _detect_max_attempts: int = 4
    _last_detect: Dict[str, Any] | None = None

    _coord_token: str = ""
    _await_tracking: bool = False

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

        self._origin_frame = int(context.scene.frame_current)

        # Defaults
        self._state = "INIT"
        self._ev = -1.0
        self._ega = 0.0
        self._dg = 4
        self._pt = max(5, int(self._pt))
        self._sus = max(8, int(self._sus))
        self._ptv = int(self._pt)
        self._mo_index = 0
        self._mov_best = 0
        self._vv = 0
        self._vf_best = 0
        self._detect_attempts = 0
        self._last_detect = None
        self._coord_token = f"bw_optimize_token_{id(self)}"
        self._await_tracking = False

        # Timer
        wm = context.window_manager
        win = getattr(context, "window", None) or getattr(bpy.context, "window", None)
        if not win:
            self.report({'ERROR'}, "Kein aktives Window – TIMER kann nicht registriert werden.")
            return {'CANCELLED'}
        try:
            if self._timer:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = wm.event_timer_add(0.2, window=win)
        wm.modal_handler_add(self)
        print("[Optimize] Start", dict(origin=self._origin_frame))
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
        if event.type == 'ESC':
            self.report({'WARNING'}, "Optimierung abgebrochen (ESC).")
            self.cancel(context)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        try:
            if self._state == "INIT":
                self._apply_flag1(context, self._pt, self._sus)
                self._state = "DETECT_TRACK"
                return {'RUNNING_MODAL'}

            if self._state == "DETECT_TRACK":
                # Detect (ein Pass; ggf. einige RUNNING-Runden)
                if self._maybe_wait_detect_lock(context):
                    return {'RUNNING_MODAL'}
                if self._detect_attempts < self._detect_max_attempts:
                    self._detect_attempts += 1
                    self._last_detect = run_detect_once(
                        context,
                        start_frame=int(self._origin_frame),
                        handoff_to_pipeline=False,
                    ) or {}
                    st = str(self._last_detect.get('status', 'READY'))
                    print(f"[Optimize][Detect] {st} attempt={self._detect_attempts}")
                    if st == 'RUNNING' and self._detect_attempts < self._detect_max_attempts:
                        return {'RUNNING_MODAL'}
                # Track starten (nur vorwärts) und auf Token warten
                if not self._await_tracking:
                    self._start_track_forward(context)
                    self._await_tracking = True
                    return {'RUNNING_MODAL'}
                # auf Token warten
                if not self._is_tracking_done(context):
                    return {'RUNNING_MODAL'}
                # fertig getrackt → Score
                self._ega = self._compute_ega(context, self._origin_frame)
                print(f"[Optimize][Score] ega={self._ega:.6f} ev={self._ev:.6f}")
                self._state = "EVAL"
                return {'RUNNING_MODAL'}

            if self._state == "EVAL":
                # ev >= 0 ?
                if self._ev < 0.0:
                    self._ev = float(self._ega)
                    self._pt = int(round(self._pt * 1.1))
                    self._sus = int(self._pt * 2)
                    self._apply_flag1(context, self._pt, self._sus)
                    # nächste Runde Korridor
                    self._reset_pass()
                    self._state = "DETECT_TRACK"
                    return {'RUNNING_MODAL'}
                # ega > ev ?
                if self._ega > self._ev:
                    self._ev = float(self._ega)
                    self._dg = 4
                    self._ptv = int(self._pt)
                    self._pt = int(round(self._pt * 1.1))
                    self._sus = int(self._pt * 2)
                    self._apply_flag1(context, self._pt, self._sus)
                    self._reset_pass()
                    self._state = "DETECT_TRACK"
                    return {'RUNNING_MODAL'}
                # else: dg - 1
                self._dg -= 1
                if self._dg >= 0:
                    self._pt = int(round(self._pt * 1.1))
                    self._sus = int(self._pt * 2)
                    self._apply_flag1(context, self._pt, self._sus)
                    self._reset_pass()
                    self._state = "DETECT_TRACK"
                    return {'RUNNING_MODAL'}
                # Korridor zu Ende → Motion-Model-Schleife
                self._pt = int(self._ptv)
                self._sus = int(self._ptv * 2)
                self._apply_flag1(context, self._pt, self._sus)
                self._mo_index = 0
                self._state = "MO_LOOP_DETECT_TRACK"
                self._reset_pass()
                return {'RUNNING_MODAL'}

            if self._state == "MO_LOOP_DETECT_TRACK":
                # mo index 0..4, jeweils: flag2 → detect/track → score → ggf. ev aktualisieren
                if self._mo_index > 4:
                    # Motion Model gewählt → VV-Loop
                    self._apply_motion_model(context, self._mov_best)
                    self._vv = 0
                    self._state = "VV_LOOP_DETECT_TRACK"
                    self._reset_pass()
                    return {'RUNNING_MODAL'}

                self._apply_motion_model(context, self._mo_index)
                return self._loop_body_detect_track(context, next_state_if_done="MO_LOOP_EVAL")

            if self._state == "MO_LOOP_EVAL":
                better = self._ega > self._ev
                if better:
                    self._ev = float(self._ega)
                    self._mov_best = int(self._mo_index)
                # mo index + 1
                self._mo_index += 1
                self._reset_pass()
                self._state = "MO_LOOP_DETECT_TRACK"
                return {'RUNNING_MODAL'}

            if self._state == "VV_LOOP_DETECT_TRACK":
                if self._vv > 4:
                    # Endbehandlung: R=G=B=vv (gleichschalten)
                    self._force_equal_rgb(context, self._vf_best)
                    self._state = "FINISH"
                    return {'RUNNING_MODAL'}
                self._apply_flag3(context, self._vv)
                return self._loop_body_detect_track(context, next_state_if_done="VV_LOOP_EVAL")

            if self._state == "VV_LOOP_EVAL":
                if self._ega > self._ev:
                    self._ev = float(self._ega)
                    self._vf_best = int(self._vv)
                self._vv += 1
                self._reset_pass()
                self._state = "VV_LOOP_DETECT_TRACK"
                return {'RUNNING_MODAL'}

            if self._state == "FINISH":
                # Sicherheit: Playhead auf Ursprungs-Frame
                self._ensure_origin_frame(context)
                self.cancel(context)
                print("[Optimize] FINISHED ev=", self._ev, "ptv=", self._ptv, "mov=", self._mov_best, "vf=", self._vf_best)
                return {'FINISHED'}

            # Fallback
            self.report({'ERROR'}, f"Unbekannter Zustand: {self._state}")
            self.cancel(context)
            return {'CANCELLED'}
        except Exception as ex:
            self.report({'ERROR'}, f"Modal crashed: {ex}")
            self.cancel(context)
            return {'CANCELLED'}

    # ------------------ Helper-Zustandsschritte ------------------
    def _loop_body_detect_track(self, context, *, next_state_if_done: str):
        # Detect + Track + Score für MO/VV-Schleifen
        if self._maybe_wait_detect_lock(context):
            return {'RUNNING_MODAL'}
        if not self._await_tracking and self._detect_attempts == 0:
            self._detect_attempts = 1
            self._last_detect = run_detect_once(
                context,
                start_frame=int(self._origin_frame),
                handoff_to_pipeline=False,
            ) or {}
            return {'RUNNING_MODAL'}
        if not self._await_tracking:
            self._start_track_forward(context)
            self._await_tracking = True
            return {'RUNNING_MODAL'}
        if not self._is_tracking_done(context):
            return {'RUNNING_MODAL'}
        # Score
        self._ega = self._compute_ega(context, self._origin_frame)
        self._state = next_state_if_done
        return {'RUNNING_MODAL'}

    def _maybe_wait_detect_lock(self, context) -> bool:
        return bool(context.scene.get("__detect_lock", False))

    def _reset_pass(self):
        self._detect_attempts = 0
        self._last_detect = None
        self._await_tracking = False

    def _start_track_forward(self, context):
        wm = context.window_manager
        try:
            if wm.get("bw_tracking_done_token", None) == self._coord_token:
                del wm["bw_tracking_done_token"]
        except Exception:
            pass
        print(f"[Optimize][Track] start token={self._coord_token}")
        track_to_scene_end_fn(
            context,
            coord_token=self._coord_token,
            start_frame=int(self._origin_frame),
            debug=False,
            first_delay=0.1,
        )

    def _is_tracking_done(self, context) -> bool:
        wm = context.window_manager
        token = wm.get("bw_tracking_done_token", None)
        if token != self._coord_token:
            return False
        try:
            del wm["bw_tracking_done_token"]
        except Exception:
            pass
        # Playhead-Reset sicherheitshalber
        self._ensure_origin_frame(context)
        return True

    def _ensure_origin_frame(self, context):
        cur = int(context.scene.frame_current)
        if cur != int(self._origin_frame):
            try:
                context.scene.frame_set(int(self._origin_frame))
            except Exception:
                context.scene.frame_current = int(self._origin_frame)

    # ------------------ Score/Flags ------------------
    def _apply_flag1(self, context, pattern: int, search: int):
        s = self._tracking_settings(context)
        s.default_pattern_size = int(pattern)
        s.default_search_size = int(search)
        # Vorgabe: margin = search
        try:
            s.default_margin = int(search)
        except Exception:
            pass
        print(f"[Optimize][Flag1] pt={pattern} sus={search}")

    def _apply_motion_model(self, context, index: int):
        models = ['Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot', 'Loc']
        s = self._tracking_settings(context)
        idx = max(0, min(index, len(models) - 1))
        s.default_motion_model = models[idx]
        print(f"[Optimize][Flag2] motion={s.default_motion_model} (idx={idx})")

    def _apply_flag3(self, context, vv_index: int):
        # Mapping laut Vorgabe
        # 0: R T, G F, B F
        # 1: R T, G T, B F
        # 2: R F, G T, B F
        # 3: R F, G T, B T
        # 4: R F, G F, B T
        s = self._tracking_settings(context)
        s.use_default_red_channel   = vv_index in (0, 1)
        s.use_default_green_channel = vv_index in (1, 2, 3)
        s.use_default_blue_channel  = vv_index in (3, 4)
        print(f"[Optimize][Flag3] vv={vv_index} RGB=({s.use_default_red_channel},{s.use_default_green_channel},{s.use_default_blue_channel})")

    def _force_equal_rgb(self, context, vv: int):
        # Schlussregel: R=G=B=vv (interpretiert als: alle Kanäle = Zustand des besten vv)
        s = self._tracking_settings(context)
        equal = vv in (0, 1, 2, 3, 4)
        s.use_default_red_channel = equal
        s.use_default_green_channel = equal
        s.use_default_blue_channel = equal
        print(f"[Optimize][Flag3-Final] equal RGB = {equal} (from vv={vv})")

    def _tracking_settings(self, context):
        space = getattr(context, 'space_data', None)
        clip = getattr(space, 'clip', None) if space else None
        if not clip:
            for c in bpy.data.movieclips:
                clip = c
                break
        if not clip:
            raise RuntimeError("Kein Movie Clip aktiv")
        return clip.tracking.settings

    def _frames_after_start(self, tr, start_frame: int) -> int:
        cnt = 0
        try:
            for m in tr.markers:
                if getattr(m, 'mute', False):
                    continue
                f = int(getattr(m, 'frame', -1))
                if f > int(start_frame):
                    cnt += 1
        except Exception:
            pass
        return cnt

    def _error_for_track(self, context, tr) -> float:
        # Falls error_value verfügbar: temporär nur diesen Track selektieren
        if error_value is None:
            return 1.0
        try:
            clip = getattr(context.space_data, 'clip', None)
            if not clip:
                for c in bpy.data.movieclips:
                    clip = c
                    break
            if not clip:
                return 1.0
            # Selection sichern
            sel = [t.select for t in clip.tracking.tracks]
            for t in clip.tracking.tracks:
                t.select = False
            tr.select = True
            val = error_value(context.scene)
            # Restore
            for t, s in zip(clip.tracking.tracks, sel):
                t.select = bool(s)
            if val is None:
                return 1.0
            return float(val) if float(val) > 1e-6 else 1.0
        except Exception:
            return 1.0

    def _compute_ega(self, context, start_frame: int) -> float:
        space = getattr(context, 'space_data', None)
        clip = getattr(space, 'clip', None) if space else None
        if not clip:
            for c in bpy.data.movieclips:
                clip = c
                break
        if not clip:
            return 0.0
        total = 0.0
        any_selected = False
        for tr in clip.tracking.tracks:
            if not getattr(tr, 'select', False):
                continue
            any_selected = True
            f_i = self._frames_after_start(tr, start_frame)
            e_i = self._error_for_track(context, tr)
            total += (float(f_i) / max(1e-6, float(e_i)))
        return total if any_selected else 0.0


# Optional: Register/Unregister – falls das Modul eigenständig getestet wird
def register():  # pragma: no cover
    bpy.utils.register_class(CLIP_OT_optimize_tracking_modal)

def unregister():  # pragma: no cover
    bpy.utils.unregister_class(CLIP_OT_optimize_tracking_modal)
