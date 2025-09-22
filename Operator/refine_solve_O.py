import bpy
import time
from bpy.types import Operator
from typing import Optional, Set

from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import (
    get_solve_average_error,
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


def _try_set(container, names, value):
    """Wie in tracker_settings: setzt erstes vorhandenes Attr (oder .solver.attr) auf value."""
    for name in names:
        if hasattr(container, name):
            try:
                setattr(container, name, value)
                return name
            except Exception:
                continue
    sub = getattr(container, "solver", None)
    if sub:
        for name in names:
            if hasattr(sub, name):
                try:
                    setattr(sub, name, value)
                    return f"solver.{name}"
                except Exception:
                    continue
    return None


def _apply_refine_set(ts, flags: Set[str]) -> None:
    """Setzt Refine so, wie es die UI kennt.
    flags enthält UI‑Items: 'FOCAL_LENGTH', 'PRINCIPAL_POINT', 'RADIAL_DISTORTION'.
    """
    if not ts:
        return
    # 1) Enum‑Set, wenn verfügbar
    try:
        if hasattr(ts, "refine_intrinsics"):
            ts.refine_intrinsics = set(flags)
    except Exception:
        pass
    # 2) Fallbacks je Flag (True/False je nach Mitgliedschaft)
    # Focal Length
    _ = _try_set(
        ts,
        (
            "refine_intrinsics_focal_length",
            "refine_focal_length",
            "refine_focal",
            "refine_focal_length_error",
        ),
        bool("FOCAL_LENGTH" in flags),
    )
    # Principal Point (Optical Center)
    _ = _try_set(
        ts,
        (
            "refine_intrinsics_principal_point",
            "refine_principal_point",
            "refine_principal",
            "refine_principal_point_x",
        ),
        bool("PRINCIPAL_POINT" in flags),
    )
    # Radial Distortion (inkl. K1 als Fallback)
    _ = _try_set(
        ts,
        (
            "refine_intrinsics_radial_distortion",
            "refine_radial_distortion",
            "refine_distortion",
            "refine_k1",
        ),
        bool("RADIAL_DISTORTION" in flags),
    )
    # Tangential lassen wir unberührt


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
    _last_ae: Optional[float] = None

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
        self._last_ae = None
        # Koordinator‑Flags initialisieren
        scn = context.scene
        try:
            scn["tco_refine_active"] = True
            scn["tco_refine_done"] = False
            scn["tco_reduce_executed"] = False  # bleibt hier immer False
            scn["tco_refine_avg_error"] = None
        except Exception:
            pass
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return self.invoke(context, None)

    def _current_flags(self) -> Set[str]:
        if self._stage <= 0:
            return {"FOCAL_LENGTH"}
        if self._stage == 1:
            return {"FOCAL_LENGTH", "PRINCIPAL_POINT"}
        return {"FOCAL_LENGTH", "PRINCIPAL_POINT", "RADIAL_DISTORTION"}

    def _finish(self, context):
        try:
            _restore_refine(self._ts, self._snap)
        except Exception:
            pass
        try:
            scn = context.scene
            scn["tco_refine_avg_error"] = float(self._last_ae) if isinstance(self._last_ae, (int, float)) else None
            scn["tco_refine_done"] = True
            scn["tco_refine_active"] = False
            scn["tco_reduce_executed"] = False
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

        if self._phase == "SET":
            _apply_refine_set(self._ts, self._current_flags())
            self._phase = "SOLVE"
            return {"RUNNING_MODAL"}

        if self._phase == "SOLVE":
            try:
                solve_camera_only(context)
            except Exception:
                pass
            self._phase = "WAIT"
            self._wait_deadline = time.perf_counter() + 10.0
            return {"RUNNING_MODAL"}

        if self._phase == "WAIT":
            try:
                try:
                    context.view_layer.update()
                except Exception:
                    pass
                ae = get_solve_average_error(context)
            except Exception:
                ae = None
            if not isinstance(ae, (int, float)) and time.perf_counter() < self._wait_deadline:
                return {"RUNNING_MODAL"}
            self._last_ae = float(ae) if isinstance(ae, (int, float)) else None
            if isinstance(self._last_ae, float) and self._last_ae <= thr:
                print(f"[RefineSolve] stage={self._stage} OK: avg_error={self._last_ae:.3f} <= thr={thr:.3f}", flush=True)
                return self._finish(context)
            # nächste Stufe oder Ende
            self._stage += 1
            if self._stage >= 3:
                # Stufen erschöpft → Ende (kein Reduce mehr hier)
                print(f"[RefineSolve] finished: avg_error={self._last_ae}", flush=True)
                return self._finish(context)
            self._phase = "SET"
            return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}


def register():
    bpy.utils.register_class(CLIP_OT_refine_solve_modal)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_refine_solve_modal)
