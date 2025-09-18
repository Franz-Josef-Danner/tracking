import bpy
from bpy.types import Operator
from typing import List, Set, Dict, Any, Optional, Tuple

from ..Helper.detect import run_detect_once as _primitive_detect_once
from ..Helper.distanze import run_distance_cleanup
from ..Helper.count import run_count_tracks, evaluate_marker_count, error_value  # type: ignore
# Optionaler Multi‑Pass Helper
try:
    from ..Helper.multi import run_multi_pass  # type: ignore
except Exception:
    run_multi_pass = None  # type: ignore

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

    def _safe_name(self, obj: Any) -> str:
        """Gibt einen robusten, UTF-8-sicheren Namen zurück."""
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
        """Sucht einen CLIP_EDITOR für Operator-Aufrufe."""
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
        """Versuche Track zu löschen; Fallback: Marker @frame löschen. Liefert (ok, reason)."""
        name = self._safe_name(tr)
        ptr = int(getattr(tr, "as_pointer")())
        # Pre-Select
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
        # Operator mit Override
        ovr = self._find_clip_editor_override(clip)
        try:
            if ovr:
                with bpy.context.temp_override(**ovr):
                    bpy.ops.clip.delete_track()
            else:
                bpy.ops.clip.delete_track()
        except Exception:
            pass
        # Verifikation
        try:
            for _t in clip.tracking.tracks:
                if int(getattr(_t, "as_pointer")()) == ptr or self._safe_name(_t) == name:
                    break
            else:
                # nicht mehr vorhanden
                try:
                    bpy.context.view_layer.update()
                except Exception:
                    pass
                return True, "track"
        except Exception:
            pass
        # Fallback: nur Marker @frame löschen
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

    def execute(self, context):
        scn = context.scene
        clip = self._resolve_clip(context)
        frame = int(getattr(scn, "frame_current", 1))

        # 0) Snapshot vor Detect: alte Tracks (Baseline)
        pre_ptrs = self._snapshot_ptrs(context)

        # 0b) Startparameter (fixer Threshold, Margin aus Scene, min_distance aus Scene/State)
        fixed_margin = int(scn.get("margin_base") or 0)
        if fixed_margin <= 0:
            w = int(getattr(clip, "size", (800, 800))[0]) if clip else 800
            patt = max(8, int(w / 100))
            fixed_margin = patt * 2
        curr_thr = 0.0001
        tco_md = scn.get("tco_detect_min_distance")
        curr_md = float(tco_md) if isinstance(tco_md, (int, float)) and float(tco_md) > 0 else float(scn.get("min_distance_base", 200.0))
        try:
            scn["kc_detect_min_distance_px"] = int(round(curr_md))
            scn["kc_min_distance_effective"] = int(round(curr_md))
        except Exception:
            pass

        # Schwellwerte (Count)
        target = 100
        for k in ("tco_detect_target", "detect_target", "marker_target", "target_new_markers"):
            v = scn.get(k)
            if isinstance(v, (int, float)) and int(v) > 0:
                target = int(v)
                break

        # Repeat aus FindLow+Jump (für Multi-Pass-Gate)
        repeat_count = 0
        try:
            repeat_count = int((scn.get("tco_last_findlowjump") or {}).get("repeat_count", 0))
        except Exception:
            repeat_count = 0
        multi_repeat_gate = int(scn.get("tco_multi_repeat_gate", 6) or 6)

        attempts = 0
        max_attempts = int(scn.get("tco_detect_max_retries", 8) or 8)
        last_eval = None
        last_dist = None
        deleted_labels_total: List[str] = []

        while attempts < max_attempts:
            # 1) Detect mit fixen Werten
            detect_res = _primitive_detect_once(
                context,
                threshold=curr_thr,
                margin=int(fixed_margin),
                min_distance=int(round(curr_md)),
                placement="FRAME",
            )

            # 2) Distanzé gegen Baseline
            dist_res = run_distance_cleanup(
                context,
                baseline_ptrs=pre_ptrs,
                frame=frame,
                min_distance=float(curr_md),
            )
            last_dist = dist_res

            # 3) Menge neuer nach Cleanup bestimmen
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

            # 4) Count evaluieren
            eval_res = evaluate_marker_count(new_ptrs_after_cleanup=new_after)
            last_eval = dict(eval_res)

            # 5) Reaktion
            deleted_labels: List[str] = []
            removed_cnt = 0
            if eval_res.get("status") == "TOO_MANY":
                # Überschuss löschen (schlechteste zuerst)
                over = max(0, int(eval_res["count"]) - int(eval_res["max"]))
                if over > 0:
                    ptr_map = self._tracks_by_ptr(context)
                    cand_tracks = [ptr_map[p] for p in new_after if p in ptr_map]
                    try:
                        cand_tracks.sort(key=lambda t: float(error_value(t)), reverse=True)
                    except Exception:
                        pass
                    for t in cand_tracks[:over]:
                        ok, how = self._delete_track_or_marker(context, clip, t, frame)
                        if ok:
                            deleted_labels.append(self._safe_name(t))
                            removed_cnt += 1
                            try:
                                new_after.discard(int(t.as_pointer()))
                            except Exception:
                                pass
                    # Recompute count after deletion
                    eval_res = {
                        "status": "ENOUGH",
                        "count": int(len(new_after)),
                        "min": int(eval_res.get("min", 0)),
                        "max": int(eval_res.get("max", 0)),
                    }
            elif eval_res.get("status") == "TOO_FEW":
                # Alle neuen wieder entfernen → saubere Wiederholung mit höherem min_distance
                ptr_map = self._tracks_by_ptr(context)
                for p in list(new_after):
                    t = ptr_map.get(p)
                    if not t:
                        continue
                    ok, how = self._delete_track_or_marker(context, clip, t, frame)
                    if ok:
                        deleted_labels.append(self._safe_name(t))
                        removed_cnt += 1
                new_after.clear()
                # min_distance für nächste Runde stufen (Formel wie zuvor)
                za = float(target)
                gm = float(0.0)  # nach Entfernen
                f_md = 1.0 - ((za - gm) / (za * (20.0 / max(1, min(7, abs(za - gm) / 10)))))
                next_md = float(curr_md) * float(f_md)
                curr_md = max(8.0, float(next_md))
                try:
                    scn["tco_detect_min_distance"] = float(curr_md)
                    scn["kc_detect_min_distance_px"] = int(round(curr_md))
                    scn["kc_min_distance_effective"] = int(round(curr_md))
                except Exception:
                    pass
                attempts += 1
                deleted_labels_total.extend(deleted_labels)
                # Persist aktuelle Telemetrie und weiter loopen
                continue
            else:  # ENOUGH
                # Gate für Multi: nur wenn Repeat hoch genug
                if run_multi_pass is not None and repeat_count >= multi_repeat_gate:
                    try:
                        core = run_multi_pass(
                            context,
                            frame=frame,
                            detect_threshold=float(curr_thr),
                            pre_ptrs=pre_ptrs,
                            repeat_count=int(repeat_count),
                        ) or {}
                    except Exception:
                        core = {"status": "FAILED"}
                    # Nach Multi erneut Distanzé und Count finalisieren
                    dist_res2 = run_distance_cleanup(
                        context,
                        baseline_ptrs=pre_ptrs,
                        frame=frame,
                        min_distance=float(curr_md),
                    )
                    last_dist = dist_res2 if isinstance(dist_res2, dict) else last_dist
                    raw_after2 = (last_dist or {}).get("new_ptrs_after_cleanup") if isinstance(last_dist, dict) else None
                    if isinstance(raw_after2, (list, tuple, set)):
                        try:
                            new_after = {int(p) for p in raw_after2}
                        except Exception:
                            new_after = set()
                    else:
                        post_ptrs = self._tracks_with_marker_at_frame(context, frame)
                        new_after = {p for p in post_ptrs if p not in pre_ptrs}
                    eval_res = evaluate_marker_count(new_ptrs_after_cleanup=new_after)
                    last_eval = dict(eval_res)
                # Final – Schleife verlassen
                deleted_labels_total.extend(deleted_labels)
                break

            # Schleife fortsetzen nach TOO_MANY-Bereinigung (zählt als Erfolg)
            deleted_labels_total.extend(deleted_labels)
            break

        # Persist Policy-Werte für nächste Runde (auch bei Abbruch)
        scn["tco_last_detect_new_count"] = int(last_eval.get("count", 0) if isinstance(last_eval, dict) else 0)
        scn["tco_detect_thr"] = float(curr_thr)
        scn["tco_detect_min_distance"] = float(curr_md)
        scn["tco_detect_margin"] = int(fixed_margin)
        try:
            scn["kc_detect_min_distance_px"] = int(round(curr_md))
        except Exception:
            pass
        scn["tco_last_count_for_formulas"] = int(last_eval.get("count", 0) if isinstance(last_eval, dict) else 0)
        scn["tco_count_for_formulas"] = int(last_eval.get("count", 0) if isinstance(last_eval, dict) else 0)

        # Optional: Gesamt-Count am Frame
        try:
            count_res = run_count_tracks(context, frame=frame)
        except Exception:
            count_res = None

        # Ergebnis zusammenstellen (IDProps‑sicher)
        safe_dist = {}
        if isinstance(last_dist, dict):
            safe_dist = dict(last_dist)
            safe_dist.pop("new_ptrs_after_cleanup", None)
            if deleted_labels_total:
                try:
                    safe_dist["deleted"] = list(safe_dist.get("deleted", [])) + deleted_labels_total
                except Exception:
                    safe_dist["deleted"] = deleted_labels_total
            safe_dist["new_after_count"] = int(last_eval.get("count", 0) if isinstance(last_eval, dict) else 0)
        result = {
            "detect": {
                "status": "READY",
                "frame": frame,
                "threshold": curr_thr,
                "new_tracks": int(scn.get("tco_last_detect_new_count", 0)),
                "margin_px": int(fixed_margin),
                "min_distance_px": int(round(curr_md)),
                "repeat_count": int(repeat_count),
                "triplet_mode": int(scn.get("_tracking_triplet_mode", 0) or 0),
            },
            "distance": safe_dist,
            "count": last_eval or {"status": "UNKNOWN", "count": 0},
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
