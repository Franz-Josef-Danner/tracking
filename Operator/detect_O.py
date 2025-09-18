import bpy
from bpy.types import Operator
from ..Helper.detect import run_detect_once as _primitive_detect_once
from ..Helper.distanze import run_distance_cleanup
from ..Helper.count import run_count_tracks, evaluate_marker_count  # type: ignore
from ..Helper.tracking_state import _get_state, _ensure_frame_entry, ABORT_AT
from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame
from ..Helper.marker_helper_main import marker_helper_main
from ..Helper.tracker_settings import apply_tracker_settings

class CLIP_OT_detect_cycle(Operator):
    bl_idname = "clip.detect_cycle"
    bl_label = "Detect Cycle (1x Detect + Distanz)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        # 1. Detect ausführen
        detect_res = _primitive_detect_once(context)
        # 2. Distance-Cleanup
        pre_ptrs = set()
        clip = getattr(context, "edit_movieclip", None)
        if clip:
            pre_ptrs = {int(t.as_pointer()) for t in getattr(clip.tracking, "tracks", [])}
        dist_res = run_distance_cleanup(context, baseline_ptrs=pre_ptrs, frame=scn.frame_current)
        # 3. Count (optional)
        count_res = None
        if callable(run_count_tracks):
            try:
                count_res = run_count_tracks(context, frame=scn.frame_current)
            except Exception as exc:
                count_res = {"status": "ERROR", "reason": str(exc)}
        # 4. Zusammenfassen
        result = {
            "detect": detect_res,
            "distance": dist_res,
            "count": count_res,
        }
        scn["tco_last_detect_cycle"] = result
        self.report({'INFO'}, f"Detect-Cycle abgeschlossen: {result}")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_detect_cycle)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_detect_cycle)
