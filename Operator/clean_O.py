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


class CLIP_OT_clean_cycle(Operator):
    bl_idname = "clip.clean_cycle"
    bl_label = "Clean Cycle (Spike+Segments+Tracks+Split)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        steps: list[dict] = []

        # 1) Spike-Filter
        thr = float(scn.get("tco_clean_track_threshold", scn.get("tco_spike_threshold", 100.0)) or 100.0)
        if run_marker_spike_filter_cycle is not None:
            try:
                run_marker_spike_filter_cycle(context, track_threshold=thr)
                steps.append({"step": "spike_filter", "status": "OK", "threshold": thr})
            except Exception as exc:
                steps.append({"step": "spike_filter", "status": "ERROR", "reason": str(exc)})
        else:
            steps.append({"step": "spike_filter", "status": "SKIPPED", "reason": "helper missing"})

        # 2) Segment-Cleanup
        min_len = int(scn.get("tco_min_seg_len", 25) or 25)
        if clean_short_segments is not None:
            try:
                clean_short_segments(context, min_len=min_len)
                steps.append({"step": "clean_short_segments", "status": "OK", "min_len": min_len})
            except Exception as exc:
                steps.append({"step": "clean_short_segments", "status": "ERROR", "reason": str(exc)})
        else:
            steps.append({"step": "clean_short_segments", "status": "SKIPPED", "reason": "helper missing"})

        # 3) Track-Cleanup
        if clean_short_tracks is not None:
            try:
                clean_short_tracks(context)
                steps.append({"step": "clean_short_tracks", "status": "OK"})
            except Exception as exc:
                steps.append({"step": "clean_short_tracks", "status": "ERROR", "reason": str(exc)})
        else:
            steps.append({"step": "clean_short_tracks", "status": "SKIPPED", "reason": "helper missing"})

        # 4) Split-Cleanup (optional)
        if recursive_split_cleanup is not None:
            try:
                # Falls der Helper einen Override benötigt, sollte dies intern gehandhabt werden
                recursive_split_cleanup(context)
                steps.append({"step": "split_cleanup", "status": "OK"})
            except Exception as exc:
                steps.append({"step": "split_cleanup", "status": "ERROR", "reason": str(exc)})
        else:
            steps.append({"step": "split_cleanup", "status": "SKIPPED", "reason": "helper missing"})

        result = {
            "status": "OK" if all(s.get("status") == "OK" or s.get("status") == "SKIPPED" for s in steps) else "WARN",
            "threshold": thr,
            "min_seg_len": min_len,
            "steps": steps,
        }
        scn["tco_last_clean_cycle"] = result
        self.report({'INFO'}, f"Clean-Cycle abgeschlossen: {result}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_clean_cycle)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_clean_cycle)
