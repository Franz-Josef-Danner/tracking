import bpy
import time
from bpy.types import Operator
from typing import Optional, Set

from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import (
    get_solve_average_error,
    run_reduce_error_tracks,
)


def _get_tracking_settings(context):
    clip = (
        getattr(context, "edit_movieclip", None)
        or getattr(getattr(context, "space_data", None), "clip", None)
        or getattr(bpy.context, "edit_movieclip", None)
    )
    if not clip:
        try:
            clip = bpy.data.movieclips[0]
        except Exception:
            clip = None
    ts = clip.tracking.settings if clip and getattr(clip, "tracking", None) else None
    return ts


def _snapshot_refine(ts) -> Optional[dict]:
    if not ts:
        return None
    snap = {}
    try:
        flags = getattr(ts, "refine_intrinsics", set())
        snap["refine_intrinsics"] = set(flags) if isinstance(flags, (set, list, tuple)) else set()
    except Exception:
        snap["refine_intrinsics"] = set()
    for name in (
        "refine_focal_length",
        "refine_principal_point",
        "refine_radial_distortion",
        "refine_tangential",
        "refine_k1", "refine_k2", "refine_k3",
    ):
        try:
            if hasattr(ts, name):
                snap[name] = bool(getattr(ts, name))
        except Exception:
            pass
    return snap


def _restore_refine(ts, snap) -> None:
    if not ts or not isinstance(snap, dict):
        return
    try:
        if "refine_intrinsics" in snap and hasattr(ts, "refine_intrinsics"):
            try:
                ts.refine_intrinsics = set(snap["refine_intrinsics"]) or set()
            except Exception:
                pass
    except Exception:
        pass
    for k, v in snap.items():
        if k == "refine_intrinsics":
            continue
        try:
            if hasattr(ts, k):
                setattr(ts, k, bool(v))
        except Exception:
            pass


def _apply_refine_set(ts, flags: Set[str]) -> None:
    """Versucht primär ts.refine_intrinsics zu setzen; fällt auf Einzel‑Checkboxen zurück."""
    if not ts:
        return
    # Versuche Set auf refine_intrinsics
    try:
        if hasattr(ts, "refine_intrinsics"):
            ts.refine_intrinsics = set(flags)
            return
    except Exception:
        pass
    # Fallback: Einzel‑Checkboxen
    try:
        if hasattr(ts, "refine_focal_length"):
            ts.refine_focal_length = ("FOCAL_LENGTH" in flags)
        if hasattr(ts, "refine_principal_point"):
            ts.refine_principal_point = ("PRINCIPAL_POINT" in flags)
        if hasattr(ts, "refine_radial_distortion"):
            ts.refine_radial_distortion = ("RADIAL_K1" in flags)
        if hasattr(ts, "refine_k1"):
            ts.refine_k1 = ("RADIAL_K1" in flags)
    except Exception:
        pass


class CLIP_OT_refine_solve_modal(Operator):
    bl_idname = "clip.refine_solve_modal"
    bl_label = "Refine Solve (F → PP → Radial)"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _stage: int
    _phase: str  # "SET" | "SOLVE" | "WAIT"
    _wait_deadline: float
    _ts = None
    _snap = None

    def _cleanup(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.10, window=context.window)
        wm.modal_handler_add(self)
        self._stage = 0
        self._phase = "SET"
        self._wait_deadline = 0.0
        self._ts = _get_tracking_settings(context)
        self._snap = _snapshot_refine(self._ts)
        # Koordinator‑Flags initialisieren (optional)
        scn = context.scene
        try:
            scn["tco_refine_active"] = True
            scn["tco_refine_done"] = False
            scn["tco_reduce_executed"] = False
        except Exception:
            pass
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def _current_flags(self) -> Set[str]:
        # Stufen: 0 -> {FOCAL}, 1 -> {FOCAL, PRINCIPAL}, 2 -> {FOCAL, PRINCIPAL, RADIAL_K1}
        if self._stage <= 0:
            return {"FOCAL_LENGTH"}
        if self._stage == 1:
            return {"FOCAL_LENGTH", "PRINCIPAL_POINT"}
        return {"FOCAL_LENGTH", "PRINCIPAL_POINT", "RADIAL_K1"}

    def _finish(self, context, reduce_executed: bool = False):
        try:
            _restore_refine(self._ts, self._snap)
        except Exception:
            pass
        try:
            scn = context.scene
            scn["tco_refine_done"] = True
            scn["tco_refine_active"] = False
            scn["tco_reduce_executed"] = bool(reduce_executed)
        except Exception:
            pass
        self._cleanup(context)
        return {"FINISHED"}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {"RUNNING_MODAL"}

        scn = context.scene
        try:
            thr = float(getattr(scn, "error_track", 2.0))
        except Exception:
            thr = 2.0

        # Phase: Flags setzen
        if self._phase == "SET":
            _apply_refine_set(self._ts, self._current_flags())
            self._phase = "SOLVE"
            return {"RUNNING_MODAL"}

        # Phase: Solve starten
        if self._phase == "SOLVE":
            try:
                solve_camera_only(context)
            except Exception:
                pass
            self._phase = "WAIT"
            self._wait_deadline = time.perf_counter() + 10.0
            return {"RUNNING_MODAL"}

        # Phase: Auf avg_error warten und entscheiden
        if self._phase == "WAIT":
            try:
                try:
                    context.view_layer.update()
                except Exception:
                    pass
                ae = get_solve_average_error(context)
            except Exception:
                ae = None
            if not isinstance(ae, (int, float)):
                if time.perf_counter() < self._wait_deadline:
                    return {"RUNNING_MODAL"}
                # Timeout → weiter
                ae = None
            # Entscheidung
            if isinstance(ae, (int, float)) and (float(ae) <= thr):
                print(f"[RefineSolve] stage={self._stage} OK: avg_error={float(ae):.3f} <= thr={thr:.3f}", flush=True)
                return self._finish(context, reduce_executed=False)
            # sonst zur nächsten Stufe
            self._stage += 1
            if self._stage >= 3:
                # Reduce Top‑5 und Flag setzen
                print("[RefineSolve] Reduce (Top5) gestartet…", flush=True)
                try:
                    res = run_reduce_error_tracks(context, max_to_delete=5)
                    try:
                        scn["tco_last_reduce_error_tracks"] = res
                    except Exception:
                        pass
                    self.report({'INFO'}, f"Reduce-Error-Tracks: deleted={int(res.get('deleted',0))}")
                except Exception as ex:
                    self.report({'WARNING'}, f"Reduce-Error-Tracks Fehler: {ex}")
                return self._finish(context, reduce_executed=True)
            # nächste Stufe fortsetzen
            self._phase = "SET"
            return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}


def register():
    bpy.utils.register_class(CLIP_OT_refine_solve_modal)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_refine_solve_modal)
