import bpy
import time
from bpy.types import Operator
from typing import List, Dict, Any, Optional

from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_solve_average_error, run_reduce_error_tracks
from ..Helper.find_max_marker_frame import run_find_max_marker_frame

DISTORTION_MODELS: List[str] = ["POLYNOMIAL", "DIVISION", "BROWN"]  # NUKE ausgelassen


def _get_clip_and_camera(context):
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
    cam = clip.tracking.camera if clip and getattr(clip, "tracking", None) else None
    return clip, cam


def _next_model(current: str) -> str:
    try:
        idx = DISTORTION_MODELS.index(str(current))
    except Exception:
        idx = 0
    return DISTORTION_MODELS[(idx + 1) % len(DISTORTION_MODELS)]


def _snapshot_disable_refine(context):
    clip, cam = _get_clip_and_camera(context)
    if not clip or not getattr(clip, "tracking", None):
        return None, None
    ts = clip.tracking.settings
    snap: Dict[str, Any] = {}
    # Enum-Flags sichern und leeren
    try:
        flags = getattr(ts, "refine_intrinsics", set())
        snap["refine_intrinsics"] = set(flags) if isinstance(flags, (set, list, tuple)) else set()
        try:
            ts.refine_intrinsics = set()
        except Exception:
            pass
    except Exception:
        pass
    # Einzel-Checkboxen robust auf False setzen
    for name in (
        "refine_focal_length",
        "refine_principal_point",
        "refine_tangential",
        "refine_radial_distortion",
        "refine_k1", "refine_k2", "refine_k3", "refine_k4", "refine_k5", "refine_k6",
    ):
        try:
            if hasattr(ts, name):
                snap[name] = bool(getattr(ts, name))
                setattr(ts, name, False)
        except Exception:
            pass
    return ts, snap


def _restore_refine(ts, snap) -> None:
    if not ts or not isinstance(snap, dict):
        return
    try:
        if "refine_intrinsics" in snap:
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


def _force_disable_refine(context) -> bool:
    clip, cam = _get_clip_and_camera(context)
    if not clip or not getattr(clip, "tracking", None):
        return False
    ts = clip.tracking.settings
    changed = False
    # Enum-Set leeren
    try:
        if hasattr(ts, "refine_intrinsics"):
            ts.refine_intrinsics = set()
            changed = True
    except Exception:
        pass
    # Einzel-/alternative Properties robust abschalten
    groups = [
        ("FOCAL_LENGTH", (
            "refine_intrinsics_focal_length",
            "refine_focal_length",
            "refine_focal",
            "refine_focal_length_error",
        )),
        ("PRINCIPAL_POINT", (
            "refine_intrinsics_principal_point",
            "refine_principal_point",
            "refine_principal",
            "refine_principal_point_x",
        )),
        ("RADIAL_DISTORTION", (
            "refine_intrinsics_radial_distortion",
            "refine_radial_distortion",
            "refine_distortion",
            "refine_k1",
        )),
        ("TANGENTIAL", (
            "refine_tangential",
            "refine_intrinsics_tangential_distortion",
            "refine_tangential_distortion",
        )),
    ]
    for _flag, names in groups:
        name_set = _try_set(ts, names, False)
        if name_set:
            changed = True
    return changed


def _force_enable_refine_all(context) -> bool:
    """Aktiviere alle Refine-Optionen (Focal, Principal, Radial, optional Tangential)."""
    clip, cam = _get_clip_and_camera(context)
    if not clip or not getattr(clip, "tracking", None):
        return False
    ts = clip.tracking.settings
    changed = False
    # Enum-Set setzen
    try:
        if hasattr(ts, "refine_intrinsics"):
            ts.refine_intrinsics = {"FOCAL_LENGTH", "PRINCIPAL_POINT", "RADIAL_DISTORTION"}
            changed = True
    except Exception:
        pass
    # Einzel-/alternative Properties robust einschalten
    groups_true = [
        ("FOCAL_LENGTH", (
            "refine_intrinsics_focal_length",
            "refine_focal_length",
            "refine_focal",
            "refine_focal_length_error",
        )),
        ("PRINCIPAL_POINT", (
            "refine_intrinsics_principal_point",
            "refine_principal_point",
            "refine_principal",
            "refine_principal_point_x",
        )),
        ("RADIAL_DISTORTION", (
            "refine_intrinsics_radial_distortion",
            "refine_radial_distortion",
            "refine_distortion",
            "refine_k1",
        )),
        ("TANGENTIAL", (
            "refine_tangential",
            "refine_intrinsics_tangential_distortion",
            "refine_tangential_distortion",
        )),
    ]
    for _flag, names in groups_true:
        name_set = _try_set(ts, names, True)
        if name_set:
            changed = True
    return changed


class CLIP_OT_solve_test(Operator):
    bl_idname = "clip.solve_test"
    bl_label = "Solve Test (2-Pass Modal)"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _state: str
    _deadline: float
    _ae: Optional[float]
    _find_result: Optional[Dict[str, Any]]
    _loops: int
    _last_reduce: Optional[Dict[str, Any]]
    _pass: int  # 0: no refine, 1: all refine

    def _cleanup(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

    def invoke(self, context, event):
        print("[SolveTest] invoke start")
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.10, window=context.window)
        wm.modal_handler_add(self)
        self._state = "INIT"
        self._deadline = 0.0
        self._ae = None
        self._find_result = None
        self._loops = 0
        self._last_reduce = None
        self._pass = 0
        try:
            context.scene["tco_solve_test_active"] = True
            context.scene["tco_restart_find"] = False
        except Exception:
            pass
        print("[SolveTest] invoke done -> RUNNING_MODAL")
        return {"RUNNING_MODAL"}

    def execute(self, context):
        print("[SolveTest] execute -> invoke")
        return self.invoke(context, None)

    def _finish(self, context, payload: Dict[str, Any]):
        scn = context.scene
        try:
            restart = bool(payload.get("restart_find", False))
            scn["tco_restart_find"] = restart
            print(f"[SolveTest] finish payload={payload} restart_find={restart}")
        except Exception:
            pass
        try:
            payload["loops"] = self._loops
            payload["last_reduce"] = self._last_reduce
            payload["find_max"] = self._find_result
            scn["tco_solve_test"] = payload
            scn["tco_solve_test_active"] = False
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
        clip, cam = _get_clip_and_camera(context)
        if not clip or not cam:
            return self._finish(context, {"status": "NO_CLIP_OR_CAMERA"})

        if self._state == "INIT":
            # Pass 0: Refine AUS, Pass 1: Refine AN
            if self._pass == 0:
                _force_disable_refine(context)
                print("[SolveTest] PASS0 (refine OFF)")
            else:
                _force_enable_refine_all(context)
                print("[SolveTest] PASS1 (refine ALL)")
            self._state = "SOLVE"
            return {"RUNNING_MODAL"}

        if self._state == "SOLVE":
            try:
                solve_camera_only(context)
            except Exception:
                pass
            self._deadline = time.perf_counter() + 10.0
            self._state = "WAIT"
            return {"RUNNING_MODAL"}

        if self._state == "WAIT":
            try:
                try:
                    context.view_layer.update()
                except Exception:
                    pass
                ae = get_solve_average_error(context)
            except Exception:
                ae = None
            if not isinstance(ae, (int, float)) and time.perf_counter() < self._deadline:
                return {"RUNNING_MODAL"}
            self._ae = float(ae) if isinstance(ae, (int, float)) else None
            print(f"[SolveTest] pass={self._pass} loop={self._loops} avg_error={self._ae} thr={thr}")
            if (self._ae is not None) and (self._ae <= thr):
                return self._finish(context, {"status": "OK", "avg_error": self._ae, "stage": ("pass0" if self._pass == 0 else "pass1"), "restart_find": False})
            self._state = "REDUCE"
            return {"RUNNING_MODAL"}

        if self._state == "REDUCE":
            # Dynamische Anzahl: n = max(1, min(10, ae/thr))
            try:
                ratio = float(self._ae) / max(1e-9, float(thr)) if self._ae is not None else 1.0
            except Exception:
                ratio = 1.0
            n_delete = int(max(1, min(10, ratio)))
            print(f"[SolveTest] reduce n={n_delete} (ratio={ratio:.3f})")
            try:
                self._last_reduce = run_reduce_error_tracks(context, max_to_delete=int(n_delete))
                try:
                    scn["tco_last_reduce_error_tracks"] = self._last_reduce
                except Exception:
                    pass
                print(f"[SolveTest] reduce_result deleted={self._last_reduce.get('deleted')} names={self._last_reduce.get('names')}")
            except Exception as ex:
                self._last_reduce = {"status": "ERROR", "reason": str(ex)}
                print(f"[SolveTest] reduce_error {ex}")
            self._state = "FINDMAX"
            return {"RUNNING_MODAL"}

        if self._state == "FINDMAX":
            try:
                self._find_result = run_find_max_marker_frame(context)
            except Exception as ex:
                self._find_result = {"status": "ERROR", "reason": str(ex)}
            status = str((self._find_result or {}).get("status", "")).upper()
            print(f"[SolveTest] find_max status={status} result={self._find_result}")
            if status == "FOUND":
                # Flag setzen und Coordinator zu FIND zurückschicken
                return self._finish(context, {"status": "RESTART_FIND", "avg_error": self._ae, "restart_find": True})
            # nicht gefunden → zum nächsten Pass / Loop
            if self._pass == 0:
                self._pass = 1
                self._state = "INIT"
                return {"RUNNING_MODAL"}
            else:
                self._pass = 0
                self._loops += 1
                self._state = "INIT"
                return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}


def register():
    bpy.utils.register_class(CLIP_OT_solve_test)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_test)
