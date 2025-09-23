import math
import time
import bpy
from bpy.types import Operator
from typing import List, Dict, Any, Optional, Tuple

from ..Helper.solve_camera import solve_camera_only
from ..Helper.reduce_error_tracks import get_solve_average_error, run_reduce_error_tracks
from ..Helper.find_max_marker_frame import run_find_max_marker_frame

ALLOWED_MODELS: Tuple[str, ...] = ("POLYNOMIAL", "DIVISION", "BROWN")  # NUKE bewusst ausgelassen

def _get_tracking_objs(context):
    clip = getattr(context.space_data, "clip", None)
    tr = getattr(clip, "tracking", None) if clip else None
    ts = getattr(tr, "settings", None) if tr else None
    tc = getattr(tr, "camera", None) if tr else None
    return ts, tc

def _get_distortion_model(context) -> Optional[str]:
    ts, tc = _get_tracking_objs(context)
    # Reihenfolge: Settings dann Camera
    for obj, attr in ((ts, "distortion_model"), (ts, "distortion"),
                      (tc, "distortion_model"), (tc, "distortion")):
        if obj and hasattr(obj, attr):
            try:
                v = getattr(obj, attr)
                if isinstance(v, str) and v:
                    v_up = v.upper()
                    print(f"[SolveTest] model_read {v_up} from {obj.__class__.__name__}.{attr}")
                    return v_up
            except Exception:
                continue
    return None

def _set_distortion_model(context, value: str) -> Optional[str]:
    ts, tc = _get_tracking_objs(context)
    val = str(value).upper()
    for obj, attr in ((ts, "distortion_model"), (ts, "distortion"),
                      (tc, "distortion_model"), (tc, "distortion")):
        if obj and hasattr(obj, attr):
            try:
                setattr(obj, attr, val)
                # Scene/UI refresh optional
                try:
                    context.view_layer.update()
                except Exception:
                    pass
                path = f"{obj.__class__.__name__}.{attr}"
                print(f"[SolveTest] model_write {val} to {path}")
                return path
            except Exception:
                continue
    print(f"[SolveTest] model_write FAILED value={val}")
    return None

def _cycle_distortion_model(context) -> Tuple[Optional[str], Optional[str]]:
    cur = _get_distortion_model(context)
    if cur not in ALLOWED_MODELS:
        nxt = ALLOWED_MODELS[0]
        where = _set_distortion_model(context, nxt)
        print(f"[SolveTest] model_switch {cur} -> {nxt} via {where} (fallback)")
        return (cur, nxt)
    i = ALLOWED_MODELS.index(cur)
    nxt = ALLOWED_MODELS[(i + 1) % len(ALLOWED_MODELS)]
    where = _set_distortion_model(context, nxt)
    print(f"[SolveTest] model_switch {cur} -> {nxt} via {where}")
    return (cur, nxt)


def _get_clip_and_camera(context):
    clip = getattr(context.space_data, "clip", None)
    cam = getattr(getattr(clip, "tracking", None), "camera", None) if clip else None
    return clip, cam


def _get_scene_focal_prefs(context):
    scn = context.scene
    use_auto = bool(getattr(scn, "tco_use_auto_focal", True))
    focal_val = float(getattr(scn, "tco_focal_override", 35.0))
    return use_auto, focal_val


def _get_focal_value(cam) -> Optional[float]:
    for name in ("focal_length", "focal", "lens"):
        try:
            v = getattr(cam, name)
        except Exception:
            continue
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def _set_focal_value(cam, val: float) -> Optional[str]:
    for name in ("focal_length", "focal", "lens"):
        if hasattr(cam, name):
            try:
                # FIX: Attributname korrekt übergeben
                setattr(cam, name, float(val))
                return name
            except Exception:
                continue
    return None


# Optional: robustere Variante für unbenutzte Hilfsfunktion
def _next_model(current: str) -> str:
    try:
        idx = ALLOWED_MODELS.index(str(current))
    except Exception:
        idx = 0
    return ALLOWED_MODELS[(idx + 1) % len(ALLOWED_MODELS)]


def _enforce_focal_override(context, focal_val: float):
    """Setzt die Brennweite exakt auf focal_val. Keine Änderung an Refine-Flags."""
    clip = getattr(context.space_data, "clip", None)
    cam = getattr(getattr(clip, "tracking", None), "camera", None) if clip else None
    if not cam:
        return None
    try:
        name = _set_focal_value(cam, focal_val)
        if name:
            print(f"[SolveTest] enforce focal {focal_val:.6f} via {name}")
        return name
    except Exception as ex:
        print(f"[SolveTest] enforce focal error: {ex}")
        return None


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
    ]
    for _flag, names in groups:
        name_set = _try_set(ts, names, False)
        if name_set:
            changed = True
    return changed


def _force_enable_refine_all(context) -> bool:
    """Aktiviere alle Refine-Optionen (Focal, Principal, Radial)."""
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
    # NEU: Focal-Grenzen
    _focal_base: Optional[float]
    _focal_low: Optional[float]
    _focal_high: Optional[float]

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
        # INIT: Focal-Attribute definieren
        self._focal_base = None
        self._focal_low = None
        self._focal_high = None
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

    def _finish(self, context, payload: dict):
        # Flags/Payload sicher schreiben und Timer abbauen
        try:
            scn = context.scene
            scn["tco_solve_test"] = payload or {}
            scn["tco_restart_find"] = bool((payload or {}).get("restart_find", False))
            scn["tco_solve_test_active"] = False
            print(f"[SolveTest] finish payload={payload} restart_find={scn['tco_restart_find']}")
        except Exception as ex:
            print(f"[SolveTest] finish flag error: {ex}")
        wm = context.window_manager
        if getattr(self, "_timer", None):
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        return {'FINISHED'}

    def cancel(self, context):
        # Bei Abbruch ebenfalls Flags zurücksetzen
        try:
            scn = context.scene
            scn["tco_solve_test_active"] = False
            scn["tco_restart_find"] = False
        except Exception:
            pass
        wm = context.window_manager
        if getattr(self, "_timer", None):
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        print("[SolveTest] cancel")
        return {'CANCELLED'}

    def modal(self, context, event):
        try:
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

            use_auto, focal_val = _get_scene_focal_prefs(context)

            if self._state == "INIT":
                # Pass 0: Refine AUS, Pass 1: Refine AN
                if self._pass == 0:
                    _force_disable_refine(context)
                    print("[SolveTest] PASS0 (refine OFF)")
                else:
                    _force_enable_refine_all(context)
                    self._init_focal_bounds_if_needed(context)
                    print("[SolveTest] PASS1 (refine ALL)")
                # Entfernt: kein hartes Erzwingen der Brennweite mehr
                self._state = "SOLVE"
                return {"RUNNING_MODAL"}

            if self._state == "SOLVE":
                # Entfernt: kein hartes Erzwingen der Brennweite mehr
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

                # Nach Refine-Solve Brennweite nur klemmen, wenn Auto-Brennweite AUS ist
                if self._pass == 1:
                    self._clamp_focal_after_refine(context)

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
                n_delete = int(max(1, min(20, ratio)))
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
                # Max-Marker suchen
                try:
                    self._find_result = run_find_max_marker_frame(context)
                except Exception as ex:
                    self._find_result = {"status": "ERROR", "error": str(ex)}
                status = (self._find_result or {}).get("status")
                print(f"[SolveTest] find_max status={status} result={self._find_result}")
                if status == "FOUND":
                    prev, nxt = _cycle_distortion_model(context)
                    payload = {
                        "status": "MODEL_SWITCH",
                        "avg_error": self._ae,
                        "previous_model": prev,
                        "next_model": nxt,
                        "restart_find": True,
                        "find_max": self._find_result,
                    }
                    return self._finish(context, payload)
                # nichts gefunden → nächster Schritt
                if self._pass == 0:
                    # weiter zu Pass 1 (alle Refines an)
                    self._pass = 1
                    self._state = "INIT"
                    return {"RUNNING_MODAL"}
                else:
                    # nach Pass 1 wieder von vorne (Pass 0)
                    self._pass = 0
                    self._loops += 1
                    self._state = "INIT"
                    return {"RUNNING_MODAL"}

            return {"RUNNING_MODAL"}
        except Exception as ex:
            print(f"[SolveTest] modal error: {ex}")
            try:
                context.scene["tco_solve_test_active"] = False
                context.scene["tco_restart_find"] = False
            except Exception:
                pass
            self._cleanup(context)
            return {'CANCELLED'}

    def _init_focal_bounds_if_needed(self, context):
        # Nur in Pass 1 initialisieren
        if self._pass != 1 or self._focal_base is not None:
            return
        use_auto, focal_val = _get_scene_focal_prefs(context)
        clip, cam = _get_clip_and_camera(context)
        if not cam:
            return
        # Baseline: bei Auto die aktuelle, sonst der UI-Wert
        base = _get_focal_value(cam) if use_auto else focal_val
        if base and base > 0:
            self._focal_base = base
            # NEU: bei use_auto=False auch ±10% setzen (kein “hard fix” mehr)
            self._focal_low = base * 0.9
            self._focal_high = base * 1.1
            print(f"[SolveTest] focal baseline set base={base:.6f} low={self._focal_low:.6f} high={self._focal_high:.6f} (use_auto={use_auto})")

    def _clamp_focal_after_refine(self, context):
        # Nur in Pass 1 prüfen – und nur, wenn Auto-Brennweite AUS ist
        use_auto, _ = _get_scene_focal_prefs(context)
        if self._pass != 1 or self._focal_base is None or use_auto:
            return
        clip, cam = _get_clip_and_camera(context)
        if not cam:
            return
        cur = _get_focal_value(cam)
        if cur is None or self._focal_low is None or self._focal_high is None:
            return
        low, high = self._focal_low, self._focal_high
        if cur < low:
            name_set = _set_focal_value(cam, low)
            print(f"[SolveTest] focal_clamp LOW cur={cur:.6f} -> {low:.6f} via {name_set}")
        elif cur > high:
            name_set = _set_focal_value(cam, high)
            print(f"[SolveTest] focal_clamp HIGH cur={cur:.6f} -> {high:.6f} via {name_set}")
        else:
            print(f"[SolveTest] focal_ok cur={cur:.6f} within [{low:.6f}, {high:.6f}]")

def register():
    bpy.utils.register_class(CLIP_OT_solve_test)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_solve_test)
