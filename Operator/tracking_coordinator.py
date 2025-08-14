# Operator/tracking_coordinator.py — Lock-Respekt für detect
import bpy
import time

from ..Helper.marker_helper_main import marker_helper_main
from ..Helper.main_to_adapt import main_to_adapt
from ..Helper.tracker_settings import apply_tracker_settings

LOCK_KEY = "__detect_lock"   # wie gehabt

# --- init ---
def _bootstrap(self, context):
    ...
    self._state = "FIND_LOW"
    self._detect_attempts = 0
    self._detect_attempts_max = 8
    self._jump_done = False             # NEU

def modal(self, context, event):
    # Detect-Lock respektieren
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

    if self._state == "INIT":
        self._state = "FIND_LOW"
        return {'RUNNING_MODAL'}

    elif self._state == "FIND_LOW":
        from ..Helper.find_low_marker_frame import run_find_low_marker_frame
        res = run_find_low_marker_frame(context) or {}
        st = res.get("status", "FAILED")
        if st == "FOUND":
            context.scene["goto_frame"] = int(res.get("frame", context.scene.frame_current))
            self._jump_done = False
            self._detect_attempts = 0
            self._state = "JUMP"        # NEU: erst springen
        elif st == "NONE":
            self._state = "SOLVE"
        else:
            self._jump_done = False
            self._detect_attempts = 0
            self._state = "JUMP"
        return {'RUNNING_MODAL'}

    elif self._state == "JUMP":         # NEU: isolierter Jump
        goto = int(context.scene.get("goto_frame", context.scene.frame_current))
        if not self._jump_done or goto != context.scene.frame_current:
            try:
                from ..Helper.jump_to_frame import run_jump_to_frame
                run_jump_to_frame(context, frame=goto)
            except Exception:
                pass
            self._jump_done = True
        # weiter zu Detect, aber ohne nochmal zu springen
        self._state = "DETECT"
        return {'RUNNING_MODAL'}

    elif self._state == "DETECT":       # NEU: reiner Detect-Loop
        goto = int(context.scene.get("goto_frame", context.scene.frame_current))
        try:
            from ..Helper.detect import run_detect_once
            res = run_detect_once(context, start_frame=goto)
        except Exception as ex:
            res = {"status": "FAILED", "reason": f"exception:{ex}"}

        st = res.get("status", "FAILED")
        if st == "READY":
            self._detect_attempts = 0
            self._state = "TRACK_FWD"
            return {'RUNNING_MODAL'}

        if st == "RUNNING":
            self._detect_attempts += 1
            if self._detect_attempts >= self._detect_attempts_max:
                self._log("[Detect] Timebox erreicht – weiter mit TRACK_FWD.")
                self._detect_attempts = 0
                self._state = "TRACK_FWD"
            # bleibt in DETECT, kein erneuter Jump
            return {'RUNNING_MODAL'}

        # FAILED → fallback
        self._log(f"[Detect] FAILED – {res.get('reason','')} → Fallback TRACK_FWD")
        self._detect_attempts = 0
        self._state = "TRACK_FWD"
        return {'RUNNING_MODAL'}

    elif self._state == "TRACK_FWD":
        try:
            bpy.ops.clip.track_markers(backwards=False)
        except Exception as ex:
            self._log(f"[TrackFwd] Fehler: {ex}")
        self._state = "TRACK_BWD" if self.do_backward else "CLEAN_SHORT"
        return {'RUNNING_MODAL'}

    elif self._state == "TRACK_BWD":
        if self.do_backward:
            try:
                bpy.ops.clip.track_markers(backwards=True)
            except Exception as ex:
                self._log(f"[TrackBwd] Fehler: {ex}")
        self._state = "CLEAN_SHORT"
        return {'RUNNING_MODAL'}

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
        try:
            from ..Helper.solve_camera import run_solve_watch_clean
            run_solve_watch_clean(context)
        except Exception as ex:
            self._log(f"[Solve] Fehler: {ex}")
        self._state = "DONE"
        return {'FINISHED'}

    elif self._state == "DONE":
        self._remove_timer(context)
        try:
            context.scene["orchestrator_active"] = False
            context.scene[LOCK_KEY] = False
        except Exception:
            pass
        return {'FINISHED'}


        return {'RUNNING_MODAL'}
