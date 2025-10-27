# Operator/master_operator.py
import bpy
import time
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from bpy.types import Operator

# ----------------------------------------------------------------------------
# Imports (direkt aus deinen bestehenden Helpern)
# ----------------------------------------------------------------------------
from ..Helper.util_format import fmt8
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_shorttest import short_test_track
from ..Helper.util_scene import set_scene_props
from ..Helper.util_reduce import (
    reduce_rot_xy,
    reduce_scale_min_max,
    reduce_rot_scale_pair,
    reduce_perspective,
)
from ..Helper.util_deeptest import (
    SCENE_DEEPTEST_ROT_XY_BEST,
    SCENE_DEEPTEST_SCALE_BEST,
    SCENE_DEEPTEST_ROT_SCALE_BEST,
    SCENE_DEEPTEST_PERSPECTIVE_BEST,
)
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.collect_selected_tracks import collect_selected_track_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.util_clip import get_current_track_names
from ..Helper.track_length_helper import get_total_track_length


# ----------------------------------------------------------------------------
# MASTER-OPERATOR
# ----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_master_operator(Operator):
    """Führt Auto-Calibrate → Detect-Adapt → Forward-Tracking → Backward-Tracking aus."""
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "Kaiserlich Tracker – Master Operator"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        report = lambda msg: self.report({'INFO'}, msg)

        print("\n=======================")
        print("[MASTER] 🚀 Startet Hauptpipeline...")
        print("=======================\n")

        # ------------------------------------------------------------
        # 1. AUTO-CALIBRATE
        # ------------------------------------------------------------
        try:
            set_all_thresholds_to_one(context)
            report("Thresholds auf 1.0 gesetzt.")
            short_test_track(context=context, tracks_to_delete=[], report_fn=report)

            base = int(scene.get("kaiserlich_len_baseline_00", 0))
            steps = {
                "STEP1": "kaiserlich_len_rot_xy_00",
                "STEP2": "kaiserlich_len_scale_00",
                "STEP3": "kaiserlich_len_rot_scale_00",
                "STEP4": "kaiserlich_len_perspective_0",
            }

            ge_list = [k for k, prop in steps.items() if float(scene.get(prop, 0)) >= base]
            vals = {k: float(scene.get(prop, 0)) for k, prop in steps.items()}

            if "STEP1" in ge_list:
                target = max(base, int(vals["STEP1"]))
                r = reduce_rot_xy(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_ROT_XY_BEST] = target
                best = r.get("best", {})
                if best.get("values"):
                    set_scene_props(scene,
                        kaiserlich_rot_thresh_x=best["values"][0],
                        kaiserlich_rot_thresh_y=best["values"][1])
                    print(f"[MASTER] RotXY reduziert auf {best['values']}")
            if "STEP2" in ge_list:
                target = max(base, int(vals["STEP2"]))
                r = reduce_scale_min_max(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_SCALE_BEST] = target
                best = r.get("best", {})
                if best.get("values"):
                    set_scene_props(scene,
                        kaiserlich_scale_thresh_min=best["values"][0],
                        kaiserlich_scale_thresh_max=best["values"][1])
                    print(f"[MASTER] Scale reduziert auf {best['values']}")
            if "STEP3" in ge_list:
                target = max(base, int(vals["STEP3"]))
                r = reduce_rot_scale_pair(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_ROT_SCALE_BEST] = target
                best = r.get("best", {})
                if best.get("values"):
                    set_scene_props(scene,
                        kaiserlich_rot_scale_thresh_rot=best["values"][0],
                        kaiserlich_rot_scale_thresh_scale=best["values"][1])
                    print(f"[MASTER] RotScale reduziert auf {best['values']}")
            if "STEP4" in ge_list:
                target = max(base, int(vals["STEP4"]))
                r = reduce_perspective(context, target_len=target, report_fn=report)
                scene[SCENE_DEEPTEST_PERSPECTIVE_BEST] = target
                best = r.get("best", {})
                if best.get("value") is not None:
                    set_scene_props(scene, kaiserlich_perspective_thresh=best["value"])
                    print(f"[MASTER] Perspective reduziert auf {best['value']}")
        except Exception as e:
            self.report({'ERROR'}, f"Auto-Calibrate Fehler: {e}")
            return {'CANCELLED'}

        # ------------------------------------------------------------
        # 2. DETECT-ADAPT
        # ------------------------------------------------------------
        try:
            clip = context.space_data.clip
            hz = clip.size[0]
            vc = clip.size[1]
            ma = clip.tracking.settings.margin
            pz = clip.tracking.settings.pattern_size
            sz = clip.tracking.settings.search_size
            md = hz * 0.025
            tr = 0.0001
            ef_target = int(scene.kaiserlich_markers_per_frame)
            pre_snapshot = snapshot_active_markers(context)

            print(f"[MASTER] DetectAdapt Start: target={ef_target}, md={md:.2f}")
            max_loops = 8
            last_md = md

            for loop in range(max_loops):
                print(f"[MASTER][Detect] Loop {loop+1}")
                detect_features(context, placement='FRAME', margin=ma,
                                threshold=tr, min_distance=int(max(1, round(last_md))))
                post_snapshot = snapshot_active_markers(context)
                alte, neue = classify_markers(pre_snapshot, post_snapshot)
                cleaned_new, deleted_old = cleanup_new_markers(
                    context, alte, neue, pz=pz, hz=hz, vc=vc
                )
                remaining = len(cleaned_new)
                if abs(remaining - ef_target) <= ef_target * 0.1:
                    print(f"[MASTER] Ziel erreicht mit {remaining} Markern.")
                    break
                ratio = ef_target / max(1, remaining)
                last_md = max(1.0, last_md / ratio)
                delete_tracks_by_names(context, [m['track'] for m in neue])
        except Exception as e:
            self.report({'ERROR'}, f"DetectAdapt Fehler: {e}")
            return {'CANCELLED'}

        # ------------------------------------------------------------
        # 3. FORWARD TRACKING
        # ------------------------------------------------------------
        try:
            print("[MASTER] ▶ Starte Vorwärts-Tracking...")
            clip = context.space_data.clip
            window, area, region, space = find_clip_editor_area(clip)
            selected = collect_selected_track_names(context)
            start_frame = context.scene.frame_start
            end_frame = context.scene.frame_end

            for frame in range(start_frame, end_frame + 1):
                space.clip_user.frame_current = frame
                context.scene.frame_current = frame
                apply_formula_on_selected_tracks(context, max_frames=5)
                track_markers_with_override(window, area, region, space,
                                            backwards=False, sequence=False)
                filter_active_tracks_at_frame(context, selected, frame)
            print("[MASTER] ✅ Vorwärts-Tracking abgeschlossen.")
        except Exception as e:
            self.report({'ERROR'}, f"Forward Tracking Fehler: {e}")
            return {'CANCELLED'}

        # ------------------------------------------------------------
        # 4. BACKWARD TRACKING
        # ------------------------------------------------------------
        try:
            print("[MASTER] ▶ Starte Rückwärts-Tracking...")
            clip = context.space_data.clip
            window, area, region, space = find_clip_editor_area(clip)
            selected = collect_selected_track_names(context)
            start_frame = context.scene.frame_start
            end_frame = context.scene.frame_end

            for frame in range(end_frame, start_frame - 1, -1):
                space.clip_user.frame_current = frame
                context.scene.frame_current = frame
                apply_formula_on_selected_tracks(context, max_frames=5)
                track_markers_with_override(window, area, region, space,
                                            backwards=True, sequence=False)
                filter_active_tracks_at_frame(context, selected, frame)
            reset_to_frame(context, start_frame)
            print("[MASTER] ✅ Rückwärts-Tracking abgeschlossen.")
        except Exception as e:
            self.report({'ERROR'}, f"Backward Tracking Fehler: {e}")
            return {'CANCELLED'}

        # ------------------------------------------------------------
        # Abschluss
        # ------------------------------------------------------------
        total_len = get_total_track_length(context)
        print(f"[MASTER] 🎯 Pipeline abgeschlossen. Gesamtlänge: {total_len}")
        report("Kaiserlich Master-Pipeline erfolgreich abgeschlossen.")
        return {'FINISHED'}


# ----------------------------------------------------------------------------
# REGISTER
# ----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_operator)
