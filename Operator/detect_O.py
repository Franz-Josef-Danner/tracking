import bpy
from bpy.types import Operator
from typing import List, Set, Dict, Any, Optional, Tuple

from ..Helper.detect import run_detect_once as _primitive_detect_once
from ..Helper.distanze import run_distance_cleanup
from ..Helper.count import run_count_tracks, evaluate_marker_count, error_value  # type: ignore

# Optional: Multi‑Pass
try:
    from ..Helper.multi import run_multi_pass  # type: ignore
except Exception:
    run_multi_pass = None  # type: ignore

# Optional: Bidirectional‑Track Operator (wird modal gestartet)
try:
    from ..Helper.bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
except Exception:
    CLIP_OT_bidirectional_track = None  # type: ignore

class CLIP_OT_detect_cycle(Operator):
    bl_idname = "clip.detect_cycle"
    bl_label = "Detect Cycle (modal)"
    bl_options = {"REGISTER", "UNDO"}

    # Runtime‑State
    _timer: object | None = None
    phase: str = "INIT"
    attempts: int = 0
    max_attempts: int = 8
    frame: int = 1
    fixed_margin: int = 0
    curr_thr: float = 0.0001
    curr_md: float = 200.0
    pre_ptrs: Set[int] | None = None
    target: int = 100
    repeat_count: int = 0
    multi_gate: int = 6
    last_dist: Dict[str, Any] | None = None
    last_eval: Dict[str, Any] | None = None
    deleted_labels_total: List[str] | None = None

    # --- Helpers (bestehend) ---
    def _resolve_clip(self, context):
        clip = getattr(context, "edit_movieclip", None)
        if not clip:
            clip = getattr(getattr(context, "space_data", None), "clip", None)
        if not clip and bpy.data.movieclips:
            try:
                clip = next(iter(bpy.data.movieclips))
            except Exception:
                clip = None
        print(f"[DETECT_O] Clip-Objekt: {repr(clip)} id={id(clip) if clip else None}")
        return clip

    def _snapshot_ptrs(self, context) -> Set[int]:
        clip = self._resolve_clip(context)
        if not clip:
            return set()
        try:
            return {int(t.as_pointer()) for t in getattr(clip.tracking, "tracks", [])}
        except Exception:
            return set()

    def _tracks_by_ptr(self, context) -> Dict[int, Any]:
        out: Dict[int, Any] = {}
        clip = self._resolve_clip(context)
        if not clip:
            return out
        for t in getattr(clip.tracking, "tracks", []):
            try:
                out[int(t.as_pointer())] = t
            except Exception:
                pass
        return out

    def _tracks_with_marker_at_frame(self, context, frame: int) -> Set[int]:
        clip = self._resolve_clip(context)
        if not clip:
            return set()
        out: Set[int] = set()
        for tr in getattr(clip.tracking, "tracks", []):
            try:
                try:
                    mk = tr.markers.find_frame(int(frame), exact=True)
                except TypeError:
                    mk = tr.markers.find_frame(int(frame))
                if mk and not getattr(mk, "mute", False):
                    out.add(int(tr.as_pointer()))
            except Exception:
                pass
        return out

    def _safe_for_scene(self, obj: Any) -> Any:
        if isinstance(obj, int):
            if obj > 2_147_483_647 or obj < -2_147_483_648:
                return str(obj)
        if isinstance(obj, dict):
            return {str(k): self._safe_for_scene(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._safe_for_scene(v) for v in obj]
        return obj

    def _safe_name(self, obj: Any) -> str:
        try:
            n = getattr(obj, "name", None)
            if isinstance(n, bytes):
                try:
                    return n.decode("utf-8", "replace")
                except Exception:
                    return "<unnamed>"
            s = str(n) if n is not None else "<unnamed>"
            try:
                s.encode("utf-8", "strict")
                return s
            except Exception:
                try:
                    return s.encode("utf-8", "replace").decode("utf-8", "replace")
                except Exception:
                    return "<unnamed>"
        except Exception:
            return "<unnamed>"

    def _find_clip_editor_override(self, clip) -> Dict[str, Any]:
        wm = bpy.context.window_manager
        if not wm:
            return {}
        for win in wm.windows:
            scr = getattr(win, "screen", None)
            if not scr:
                continue
            for area in scr.areas:
                if getattr(area, "type", "") != "CLIP_EDITOR":
                    continue
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return {
                        "window": win,
                        "area": area,
                        "region": region,
                        "space_data": space,
                        "edit_movieclip": clip,
                        "scene": bpy.context.scene,
                    }
        return {}

    def _delete_track_or_marker(self, context, clip, tr, frame: int) -> Tuple[bool, str]:
        name = self._safe_name(tr)
        ptr = int(getattr(tr, "as_pointer")())
        try:
            for _t in clip.tracking.tracks:
                _t.select = False
            tr.select = True
            try:
                mk = tr.markers.find_frame(int(frame), exact=True)
            except TypeError:
                mk = tr.markers.find_frame(int(frame))
            if mk:
                try:
                    mk.select = True
                except Exception:
                    pass
        except Exception:
            pass
        ovr = self._find_clip_editor_override(clip)
        try:
            if ovr:
                with bpy.context.temp_override(**ovr):
                    bpy.ops.clip.delete_track()
            else:
                bpy.ops.clip.delete_track()
        except Exception:
            pass
        try:
            for _t in clip.tracking.tracks:
                if int(getattr(_t, "as_pointer")()) == ptr or self._safe_name(_t) == name:
                    break
            else:
                try:
                    bpy.context.view_layer.update()
                except Exception:
                    pass
                return True, "track"
        except Exception:
            pass
        try:
            tr.markers.delete_frame(int(frame))
            try:
                chk = tr.markers.find_frame(int(frame), exact=True)
            except TypeError:
                chk = tr.markers.find_frame(int(frame))
            if not chk:
                try:
                    bpy.context.view_layer.update()
                except Exception:
                    pass
                return True, "marker"
        except Exception:
            pass
        return False, "failed"

    # --- Modal Lifecycle ---
    def execute(self, context):
        scn = context.scene
        clip = self._resolve_clip(context)
        self.frame = int(getattr(scn, "frame_current", 1))
        self.pre_ptrs = self._snapshot_ptrs(context)
        # Parameter
        self.curr_thr = 0.0001
        mb = int(scn.get("margin_base") or 0)
        if mb <= 0:
            w = int(getattr(clip, "size", (800, 800))[0]) if clip else 800
            mb = max(8, int(w / 100)) * 2
        self.fixed_margin = int(mb)
        tco_md = scn.get("tco_detect_min_distance")
        self.curr_md = float(tco_md) if isinstance(tco_md, (int, float)) and float(tco_md) > 0 else float(scn.get("min_distance_base", 200.0))
        # Ziele / Gates
        self.target = 100
        for k in ("tco_detect_target", "detect_target", "marker_target", "target_new_markers"):
            v = scn.get(k)
            if isinstance(v, (int, float)) and int(v) > 0:
                self.target = int(v)
                break
        try:
            self.repeat_count = int((scn.get("tco_last_findlowjump") or {}).get("repeat_count", 0))
        except Exception:
            self.repeat_count = 0
        self.multi_gate = int(scn.get("tco_multi_repeat_gate", 6) or 6)
        self.max_attempts = int(scn.get("tco_detect_max_retries", 8) or 8)
        self.attempts = 0
        self.deleted_labels_total = []
        self.last_dist = None
        self.last_eval = None
        # Publish
        try:
            scn["kc_detect_min_distance_px"] = int(round(self.curr_md))
            scn["kc_min_distance_effective"] = int(round(self.curr_md))
            scn["tco_detect_active"] = True
        except Exception:
            pass
        # Log Start
        try:
            self.report({'INFO'}, f"[DetectO] START f={self.frame} thr={self.curr_thr:.6f} margin={self.fixed_margin} md={int(self.curr_md)} target={self.target} repeat={self.repeat_count}")
        except Exception:
            pass
        # Timer
        wm = context.window_manager
        win = getattr(context, "window", None) or getattr(bpy.context, "window", None)
        try:
            self._timer = wm.event_timer_add(0.10, window=win) if win else wm.event_timer_add(0.10)
        except Exception:
            self._timer = wm.event_timer_add(0.10)
        wm.modal_handler_add(self)
        self.phase = "DETECT"
        return {'RUNNING_MODAL'}

    def _finish(self, context, status_ok: bool = True):
        scn = context.scene
        # Persist Policy
        scn["tco_detect_thr"] = float(self.curr_thr)
        scn["tco_detect_min_distance"] = float(self.curr_md)
        scn["tco_detect_margin"] = int(self.fixed_margin)
        cnt = int(self.last_eval.get("count", 0) if isinstance(self.last_eval, dict) else 0)
        scn["tco_last_detect_new_count"] = cnt
        scn["tco_last_count_for_formulas"] = cnt
        scn["tco_count_for_formulas"] = cnt
        # Ergebnis zusammensetzen
        safe_dist = {}
        if isinstance(self.last_dist, dict):
            safe_dist = dict(self.last_dist)
            safe_dist.pop("new_ptrs_after_cleanup", None)
            if self.deleted_labels_total:
                try:
                    safe_dist["deleted"] = list(safe_dist.get("deleted", [])) + list(self.deleted_labels_total)
                except Exception:
                    safe_dist["deleted"] = list(self.deleted_labels_total)
            safe_dist["new_after_count"] = int(self.last_eval.get("count", 0) if isinstance(self.last_eval, dict) else 0)
        result = {
            "detect": {
                "status": "READY",
                "frame": int(self.frame),
                "threshold": float(self.curr_thr),
                "new_tracks": int(scn.get("tco_last_detect_new_count", 0)),
                "margin_px": int(self.fixed_margin),
                "min_distance_px": int(round(self.curr_md)),
                "repeat_count": int(self.repeat_count),
                "triplet_mode": int(scn.get("_tracking_triplet_mode", 0) or 0),
            },
            "distance": safe_dist,
            "count": self.last_eval or {"status": "UNKNOWN", "count": 0},
        }
        try:
            result["count_frame"] = run_count_tracks(context, frame=self.frame)
        except Exception:
            pass
        scn["tco_last_detect_cycle"] = self._safe_for_scene(result)
        try:
            scn["tco_detect_active"] = False
        except Exception:
            pass
        # Timer entfernen
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None
        try:
            self.report({'INFO'}, f"[DetectO] END status={self.last_eval.get('status') if isinstance(self.last_eval, dict) else '?'} count={int(self.last_eval.get('count',0)) if isinstance(self.last_eval, dict) else 0} md={int(self.curr_md)} attempts={self.attempts}")
        except Exception:
            pass
        return {'FINISHED' if status_ok else 'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            try:
                self.report({'WARNING'}, "[DetectO] ESC pressed – cancel")
            except Exception:
                pass
            return self._finish(context, status_ok=False)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        scn = context.scene
        clip = self._resolve_clip(context)
        # DETECT
        if self.phase == "DETECT":
            try:
                self.report({'INFO'}, f"[DetectO] DETECT thr={self.curr_thr:.6f} margin={self.fixed_margin} md={int(self.curr_md)} attempt={self.attempts+1}/{self.max_attempts}")
            except Exception:
                pass
            _ = _primitive_detect_once(
                context,
                threshold=self.curr_thr,
                margin=int(self.fixed_margin),
                min_distance=int(round(self.curr_md)),
                placement="FRAME",
            )
            self.phase = "DISTANZE"
            return {'RUNNING_MODAL'}
        # DISTANZE
        if self.phase == "DISTANZE":
            try:
                self.report({'INFO'}, f"[DetectO] DISTANZE md={int(self.curr_md)} baseline={len(self.pre_ptrs or [])}")
            except Exception:
                pass
            self.last_dist = run_distance_cleanup(
                context,
                baseline_ptrs=self.pre_ptrs or set(),
                frame=self.frame,
                min_distance=float(self.curr_md),
                # Wichtig: Neue Tracks nach Cleanup selektiert lassen
                distance_unit="pixel",
                require_selected_new=True,
                include_muted_old=False,
                select_remaining_new=True,
                verbose=True,
            )
            self.phase = "COUNT"
            return {'RUNNING_MODAL'}
        # COUNT
        if self.phase == "COUNT":
            raw_after = self.last_dist.get("new_ptrs_after_cleanup") if isinstance(self.last_dist, dict) else None
            if isinstance(raw_after, (list, tuple, set)):
                try:
                    new_after = {int(p) for p in raw_after}
                except Exception:
                    new_after = set()
            else:
                post_ptrs = self._tracks_with_marker_at_frame(context, self.frame)
                base = self.pre_ptrs or set()
                new_after = {p for p in post_ptrs if p not in base}
            self.last_eval = evaluate_marker_count(new_ptrs_after_cleanup=new_after)
            status = str(self.last_eval.get("status", "")).upper()
            try:
                self.report({'INFO'}, f"[DetectO] COUNT status={status} count={int(self.last_eval.get('count',0))} band=[{int(self.last_eval.get('min',0))}..{int(self.last_eval.get('max',0))}]")
            except Exception:
                pass
            # TOO_MANY: kürzen
            if status == "TOO_MANY":
                over = max(0, int(self.last_eval.get("count", 0)) - int(self.last_eval.get("max", 0)))
                removed = 0
                if over > 0:
                    ptr_map = self._tracks_by_ptr(context)
                    cand_tracks = [ptr_map[p] for p in new_after if p in ptr_map]
                    try:
                        cand_tracks.sort(key=lambda t: float(error_value(t)), reverse=True)
                    except Exception:
                        pass
                    for t in cand_tracks[:over]:
                        ok, _how = self._delete_track_or_marker(context, clip, t, self.frame)
                        if ok:
                            (self.deleted_labels_total or []).append(self._safe_name(t))
                            removed += 1
                            try:
                                new_after.discard(int(t.as_pointer()))
                            except Exception:
                                pass
                    # Nach dem Trimmen: verbleibende NEUE Tracks wieder selektieren
                    try:
                        ptrs_left = set(new_after)
                        clip2 = self._resolve_clip(context)
                        trk2 = getattr(clip2, "tracking", None) if clip2 else None
                        if trk2 and hasattr(trk2, "tracks"):
                            for _t in trk2.tracks:
                                try:
                                    _t.select = (int(_t.as_pointer()) in ptrs_left)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    self.last_eval = {
                        "status": "ENOUGH",
                        "count": int(len(new_after)),
                        "min": int(self.last_eval.get("min", 0)),
                        "max": int(self.last_eval.get("max", 0)),
                    }
                try:
                    self.report({'INFO'}, f"[DetectO] TRIM too_many removed={removed}")
                except Exception:
                    pass
                return self._finish(context, status_ok=True)
            # TOO_FEW: alle neuen löschen, md stufen, retry falls Budget da
            if status == "TOO_FEW" and self.attempts + 1 < self.max_attempts:
                removed = 0
                ptr_map = self._tracks_by_ptr(context)
                for p in list(new_after):
                    t = ptr_map.get(p)
                    if not t:
                        continue
                    ok, _how = self._delete_track_or_marker(context, clip, t, self.frame)
                    if ok:
                        (self.deleted_labels_total or []).append(self._safe_name(t))
                        removed += 1
                za = float(self.target)
                gm = 0.0
                f_md = 1.0 - ((za - gm) / (za * (20.0 / max(1, min(7, abs(za - gm) / 10)))))
                self.curr_md = max(8.0, float(self.curr_md) * float(f_md))
                try:
                    scn["tco_detect_min_distance"] = float(self.curr_md)
                    scn["kc_detect_min_distance_px"] = int(round(self.curr_md))
                    scn["kc_min_distance_effective"] = int(round(self.curr_md))
                except Exception:
                    pass
                self.attempts += 1
                try:
                    self.report({'INFO'}, f"[DetectO] RETRY too_few removed={removed} md_next={int(self.curr_md)} attempt={self.attempts}/{self.max_attempts}")
                except Exception:
                    pass
                self.phase = "DETECT"
                return {'RUNNING_MODAL'}
            # ENOUGH: optional Multi
            if status == "ENOUGH" and run_multi_pass is not None and self.repeat_count >= self.multi_gate:
                try:
                    self.report({'INFO'}, f"[DetectO] MULTI start repeat={self.repeat_count} gate={self.multi_gate}")
                except Exception:
                    pass
                try:
                    _ = run_multi_pass(
                        context,
                        frame=self.frame,
                        detect_threshold=float(self.curr_thr),
                        pre_ptrs=self.pre_ptrs or set(),
                        repeat_count=int(self.repeat_count),
                    )
                except Exception:
                    pass
                self.phase = "DISTANZE"
                return {'RUNNING_MODAL'}
            try:
                self.report({'INFO'}, "[DetectO] DONE (ENOUGH)")
            except Exception:
                pass
            return self._finish(context, status_ok=True)

        # Fallback
        return self._finish(context, status_ok=True)


def register():
    bpy.utils.register_class(CLIP_OT_detect_cycle)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_detect_cycle)
