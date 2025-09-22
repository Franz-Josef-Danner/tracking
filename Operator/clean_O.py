import bpy
from bpy.types import Operator

# Helper-Imports
try:
    from ..Helper.spike_filter_cycle import run_marker_spike_filter_cycle  # type: ignore
except Exception:
    run_marker_spike_filter_cycle = None  # type: ignore

try:
    from ..Helper.clean_short_segments import clean_short_segments  # type: ignore
except Exception:
    clean_short_segments = None  # type: ignore

try:
    from ..Helper.clean_short_tracks import clean_short_tracks  # type: ignore
except Exception:
    clean_short_tracks = None  # type: ignore

try:
    from ..Helper.split_cleanup import recursive_split_cleanup  # type: ignore
except Exception:
    recursive_split_cleanup = None  # type: ignore


def _get_active_clip(context):
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _count_total_markers(clip) -> int:
    try:
        trk = getattr(getattr(clip, "tracking", None), "tracks", [])
        return sum(len(getattr(t, "markers", [])) for t in trk)
    except Exception:
        return 0


class CLIP_OT_clean_cycle(Operator):
    bl_idname = "clip.clean_cycle"
    bl_label = "Clean Cycle (Spike+Segments+Tracks+Split)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        steps: list[dict] = []
        total_markers_deleted = 0

        # 1) Spike-Filter
        thr = float(scn.get("tco_clean_track_threshold", scn.get("tco_spike_threshold", 100.0)) or 100.0)
        if run_marker_spike_filter_cycle is not None:
            try:
                res = run_marker_spike_filter_cycle(context, track_threshold=thr)
                # Key je nach Aktion (Default: DELETE → 'deleted')
                affected = int(res.get("deleted") or res.get("muted") or res.get("selected") or 0)
                cleaned_markers = int(res.get("cleaned_markers", 0) or 0)
                total_markers_deleted += int(max(0, affected)) + int(max(0, cleaned_markers))
                steps.append({
                    "step": "spike_filter",
                    "status": str(res.get("status", "OK")),
                    "threshold": float(thr),
                    "affected_markers": int(affected),
                    "segments_removed": int(res.get("cleaned_segments", 0) or 0),
                    "markers_removed_in_segments": int(cleaned_markers),
                })
            except Exception as exc:
                steps.append({"step": "spike_filter", "status": "ERROR", "reason": str(exc), "threshold": float(thr)})
        else:
            steps.append({"step": "spike_filter", "status": "SKIPPED", "reason": "helper missing", "threshold": float(thr)})

        # 2) Segment-Cleanup
        min_len = int(scn.get("tco_min_seg_len", 25) or 25)
        if clean_short_segments is not None:
            try:
                res2 = clean_short_segments(context, min_len=min_len)
                m_removed = int((res2 or {}).get("markers_removed", 0) or 0)
                total_markers_deleted += int(max(0, m_removed))
                steps.append({
                    "step": "clean_short_segments",
                    "status": str((res2 or {}).get("status", "OK")),
                    "min_len": int(min_len),
                    "segments_removed": int((res2 or {}).get("segments_removed", 0) or 0),
                    "markers_removed": int(m_removed),
                    "tracks_emptied": int((res2 or {}).get("tracks_emptied", 0) or 0),
                    "estimated_removed": int((res2 or {}).get("estimated_removed", 0) or 0),
                })
            except Exception as exc:
                steps.append({"step": "clean_short_segments", "status": "ERROR", "reason": str(exc), "min_len": int(min_len)})
        else:
            steps.append({"step": "clean_short_segments", "status": "SKIPPED", "reason": "helper missing", "min_len": int(min_len)})

        # 3) Track-Cleanup
        if clean_short_tracks is not None:
            try:
                processed, affected_tracks = clean_short_tracks(context)
                steps.append({
                    "step": "clean_short_tracks",
                    "status": "OK",
                    "tracks_processed": int(processed),
                    "tracks_deleted": int(affected_tracks),
                })
            except Exception as exc:
                steps.append({"step": "clean_short_tracks", "status": "ERROR", "reason": str(exc)})
        else:
            steps.append({"step": "clean_short_tracks", "status": "SKIPPED", "reason": "helper missing"})

        # 4) Split-Cleanup (optional) – Marker-Delta vor/nach messen
        if recursive_split_cleanup is not None:
            try:
                clip = _get_active_clip(context)
                before_markers = _count_total_markers(clip) if clip else 0
                # Falls der Helper einen Override benötigt, sollte dies intern gehandhabt werden
                recursive_split_cleanup(context)
                after_markers = _count_total_markers(clip) if clip else 0
                delta = max(0, int(before_markers) - int(after_markers))
                total_markers_deleted += int(delta)
                steps.append({
                    "step": "split_cleanup",
                    "status": "OK",
                    "markers_deleted": int(delta),
                    "markers_before": int(before_markers),
                    "markers_after": int(after_markers),
                })
            except Exception as exc:
                steps.append({"step": "split_cleanup", "status": "ERROR", "reason": str(exc)})
        else:
            steps.append({"step": "split_cleanup", "status": "SKIPPED", "reason": "helper missing"})

        result = {
            "status": "OK" if all(s.get("status") in {"OK", "SKIPPED"} for s in steps) else "WARN",
            "threshold": float(thr),
            "min_seg_len": int(min_len),
            "markers_deleted_total": int(total_markers_deleted),
            "steps": steps,
        }
        try:
            scn["tco_last_clean_cycle"] = result
        except Exception:
            # Fallback: primitive Felder
            try: scn["tco_last_clean_status"] = str(result.get("status"))
            except Exception: pass
            try: scn["tco_last_clean_markers_deleted_total"] = int(result.get("markers_deleted_total", 0) or 0)
            except Exception: pass
        self.report({'INFO'}, f"Clean-Cycle abgeschlossen: {result}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_clean_cycle)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_clean_cycle)
