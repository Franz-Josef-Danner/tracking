import bpy
from bpy.types import Operator
from typing import List, Set, Dict, Any

from ..Helper.detect import run_detect_once as _primitive_detect_once
from ..Helper.distanze import run_distance_cleanup
from ..Helper.count import run_count_tracks, evaluate_marker_count, error_value  # type: ignore

class CLIP_OT_detect_cycle(Operator):
    bl_idname = "clip.detect_cycle"
    bl_label = "Detect Cycle (1x Detect + Distanz)"
    bl_options = {"REGISTER", "UNDO"}

    def _resolve_clip(self, context):
        clip = getattr(context, "edit_movieclip", None)
        if not clip:
            clip = getattr(getattr(context, "space_data", None), "clip", None)
        if not clip and bpy.data.movieclips:
            try:
                clip = next(iter(bpy.data.movieclips))
            except Exception:
                clip = None
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
        """Sanitisiert Werte für Scene-IDProperties (kein 64-bit Pointer-Int)."""
        if isinstance(obj, int):
            if obj > 2_147_483_647 or obj < -2_147_483_648:
                return str(obj)
        if isinstance(obj, dict):
            return {str(k): self._safe_for_scene(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._safe_for_scene(v) for v in obj]
        return obj

    def execute(self, context):
        scn = context.scene
        clip = self._resolve_clip(context)
        frame = int(getattr(scn, "frame_current", 1))

        # Baseline vor Detect: Pointer-Snapshot aller Tracks
        pre_ptrs = self._snapshot_ptrs(context)

        # Operative Parameter
        fixed_margin = int(scn.get("margin_base") or 0)
        if fixed_margin <= 0:
            w = int(getattr(clip, "size", (800, 800))[0]) if clip else 800
            patt = max(8, int(w / 100))
            fixed_margin = patt * 2
        curr_thr = 0.0001  # fixer Threshold
        tco_md = scn.get("tco_detect_min_distance")
        if isinstance(tco_md, (int, float)) and float(tco_md) > 0.0:
            curr_md = float(tco_md)
        else:
            base_md = scn.get("min_distance_base")
            curr_md = float(base_md if base_md is not None else 200.0)
        try:
            scn["kc_detect_min_distance_px"] = int(round(curr_md))
        except Exception:
            pass

        # 1) Detect ausführen mit Policy-Parametern
        detect_res = _primitive_detect_once(
            context,
            threshold=curr_thr,
            margin=int(fixed_margin),
            min_distance=int(round(curr_md)),
            placement="FRAME",
        )

        # 2) Distance-Cleanup mit Baseline (min_distance=None → interne Scene-Werte nutzen)
        dist_res = run_distance_cleanup(context, baseline_ptrs=pre_ptrs, frame=frame, min_distance=None)

        # 3) Neue Tracks nach Cleanup bestimmen
        new_after: Set[int]
        raw_after = dist_res.get("new_ptrs_after_cleanup") if isinstance(dist_res, dict) else None
        if isinstance(raw_after, (list, tuple, set)):
            try:
                new_after = {int(p) for p in raw_after}
            except Exception:
                new_after = set()
        else:
            post_ptrs = self._tracks_with_marker_at_frame(context, frame)
            new_after = {p for p in post_ptrs if p not in pre_ptrs}

        # 4) Anzahl evaluieren und ggf. reagieren
        eval_res = evaluate_marker_count(new_ptrs_after_cleanup=new_after)
        deleted_labels: List[str] = []
        removed_cnt = 0

        # TOO_MANY → schlechte löschen (wie Alt-Coordinator)
        if eval_res.get("status") == "TOO_MANY":
            to_delete = max(0, int(eval_res["count"]) - int(eval_res["max"]))
            if to_delete > 0:
                ptr_map = self._tracks_by_ptr(context)
                cand_tracks = [ptr_map[p] for p in new_after if p in ptr_map]
                try:
                    cand_tracks.sort(key=lambda t: float(error_value(t)), reverse=True)
                except Exception:
                    pass
                for t in cand_tracks[:to_delete]:
                    try:
                        deleted_labels.append(getattr(t, "name", "<unnamed>"))
                        getattr(clip.tracking.tracks, "remove")(t)
                        removed_cnt += 1
                        try:
                            new_after.discard(int(t.as_pointer()))
                        except Exception:
                            pass
                    except Exception:
                        pass
                eval_res = {
                    "status": "ENOUGH",
                    "count": int(len(new_after)),
                    "min": int(eval_res.get("min", 0)),
                    "max": int(eval_res.get("max", 0)),
                }

        # Distance-Result anreichern (ohne 64-bit Pointer zu persistieren)
        safe_dist = {}
        if isinstance(dist_res, dict):
            safe_dist = dict(dist_res)
            safe_dist.pop("new_ptrs_after_cleanup", None)
            safe_dist.setdefault("deleted", [])
            if deleted_labels:
                try:
                    safe_dist["deleted"] = list(safe_dist.get("deleted", [])) + deleted_labels
                except Exception:
                    safe_dist["deleted"] = deleted_labels
            try:
                safe_dist["removed"] = int(safe_dist.get("removed", 0)) + int(removed_cnt)
            except Exception:
                safe_dist["removed"] = int(removed_cnt)
            safe_dist["new_after_count"] = int(len(new_after))
        else:
            safe_dist = {"status": str(dist_res), "new_after_count": int(len(new_after)), "deleted": deleted_labels, "removed": int(removed_cnt)}

        # 5) Policy-Werte für die NÄCHSTE Runde stufen und persistieren
        gm_for_formulas = float(eval_res.get("count", 0))
        target = 100
        for k in ("tco_detect_target", "detect_target", "marker_target", "target_new_markers"):
            v = scn.get(k)
            if isinstance(v, (int, float)) and int(v) > 0:
                target = int(v)
                break
        za = float(target)
        gm = float(gm_for_formulas)
        f_md = 1.0 - ((za - gm) / (za * (20.0 / max(1, min(7, abs(za - gm) / 10)))))
        next_md = float(curr_md) * float(f_md)
        scn["tco_last_detect_new_count"] = int(gm_for_formulas)
        scn["tco_detect_thr"] = float(curr_thr)
        scn["tco_detect_min_distance"] = float(next_md)
        scn["tco_detect_margin"] = int(fixed_margin)
        try:
            scn["kc_detect_min_distance_px"] = int(round(next_md))
        except Exception:
            pass
        scn["tco_last_count_for_formulas"] = int(gm_for_formulas)
        scn["tco_count_for_formulas"] = int(gm_for_formulas)

        # 6) Optional: Gesamt-Count am Frame (nur informativ)
        count_res = None
        try:
            count_res = run_count_tracks(context, frame=frame)
        except Exception:
            count_res = None

        # 7) Zusammenfassen – ohne große Integers in IDProps
        result = {
            "detect": detect_res,
            "distance": safe_dist,
            "count": eval_res,
        }
        if count_res is not None:
            result["count_frame"] = count_res

        scn["tco_last_detect_cycle"] = self._safe_for_scene(result)
        self.report({'INFO'}, f"Detect-Cycle abgeschlossen: {result}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_detect_cycle)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_detect_cycle)
