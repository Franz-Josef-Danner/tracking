import bpy
import time
from typing import Any, Dict, Optional, Tuple
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.util_clip import get_active_clip
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.util_scene import set_scene_props
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.newmarker import classify_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.detect import detect_features
from ..Helper.cleaneup import cleanup_new_markers

# ---- Szenen-Keys ------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"

class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    bl_idname = "kaiserlich_tracker.deep_test_operator"
    bl_label = "Kaiserlich Tracker — Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    _reduction_factors = [0.95, 0.50, 0.20, 0.10, 0.05, 0.02, 0.01]
    _min_threshold = 0.00001

    def execute(self, context: Context):
        scene = context.scene
        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        print("\n[Kaiserlich Tracker][DeepTest] Starte Deep-Threshold-Test …")

        base_length = self._track_and_measure(context)
        scene[SCENE_TOTAL_TRACK_LEN_BASE] = base_length
        print(f"[Kaiserlich Tracker][DeepTest] Baseline-Länge = {base_length}")

        target_step1 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP1, 0))
        target_step2 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP2, 0))
        target_step3 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP3, 0))
        target_step4 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP4, 0))

        results: Dict[str, float] = {}

        print("[Kaiserlich Tracker][DeepTest] → Test Rotations-Threshold (X/Y)")
        rot_x, rot_y = self._test_rot_pair(context, target_step1, clip)
        results['kaiserlich_rot_thresh_x'] = rot_x
        results['kaiserlich_rot_thresh_y'] = rot_y

        print("[Kaiserlich Tracker][DeepTest] → Test Scale-Min")
        scale_min = self._test_single_threshold(context, 'kaiserlich_scale_thresh_min', target_step2,
                                                freeze_others={'kaiserlich_scale_thresh_max': 1.0})
        print("[Kaiserlich Tracker][DeepTest] → Test Scale-Max")
        scale_max = self._test_single_threshold(context, 'kaiserlich_scale_thresh_max', target_step2,
                                                freeze_others={'kaiserlich_scale_thresh_min': 1.0})
        results['kaiserlich_scale_thresh_min'] = scale_min
        results['kaiserlich_scale_thresh_max'] = scale_max

        print("[Kaiserlich Tracker][DeepTest] → Test Rot/Scale-Paar")
        rot_scale_rot, rot_scale_scale = self._test_rot_scale_pair(context, target_step3)
        results['kaiserlich_rot_scale_thresh_rot'] = rot_scale_rot
        results['kaiserlich_rot_scale_thresh_scale'] = rot_scale_scale

        print("[Kaiserlich Tracker][DeepTest] → Test Perspective")
        perspective = self._test_single_threshold(context, 'kaiserlich_perspective_thresh', target_step4,
                                                  freeze_others=results)
        results['kaiserlich_perspective_thresh'] = perspective

        set_scene_props(scene, **results)
        self.report({'INFO'}, "Deep Test abgeschlossen.")
        return {'FINISHED'}

    def _track_and_measure(self, context: Context) -> int:
        scene = context.scene
        clip = get_active_clip(context)
        if not clip or not clip.tracking:
            print("[DeepTest] ❌ Kein Tracking-Clip.")
            return 0

        hz, vc = clip.size[0], clip.size[1]
        tracking = clip.tracking

        # Pattern-Size aus detect_adapt-artigem Bootstrap
        ma = getattr(tracking.settings, "margin", 100)
        pz = getattr(tracking.settings, "pattern_size", 50)

        ef_target = int(scene.get("kaiserlich_markers_per_frame", 150))
        tolerance = ef_target * 0.1
        min_distance = max(1, int(hz * 0.05))

        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            print("[DeepTest] ❌ Kein CLIP_EDITOR-Kontext.")
            return 0

        start_frame = scene.frame_start
        current_frame = scene.frame_current
        scene.frame_current = start_frame
        space.clip_user.frame_current = start_frame

        pre_snapshot = snapshot_active_markers(context)
        baseline_tracks = {t.name for t in tracking.tracks}

        loop = 0
        max_loops = 5
        final_tracks = []

        while loop < max_loops:
            loop += 1
            detect_features(context, placement='FRAME', margin=ma, threshold=0.01, min_distance=min_distance)

            post_snapshot = snapshot_active_markers(context)
            old, new = classify_markers(pre_snapshot, post_snapshot)

            cleaned_new, _ = cleanup_new_markers(context, old, new, pz=pz, hz=hz, vc=vc)
            print(f"[DeepTest] LOOP {loop}: Marker = {len(cleaned_new)}, Ziel = {ef_target}")

            if abs(len(cleaned_new) - ef_target) <= tolerance:
                final_tracks = [m['track'] for m in cleaned_new]
                break

            delete_tracks_by_names(context, [m['track'] for m in new])
            min_distance = int(min_distance * 1.2) if len(cleaned_new) > ef_target else max(1, int(min_distance * 0.8))

        if not final_tracks:
            print("[DeepTest] ❌ Kein finaler Track gefunden.")
            return 0

        for tr in tracking.tracks:
            tr.select = tr.name in final_tracks
            tr.mute = False

        track_markers_with_override(window, area, region, space, backwards=False, sequence=True)
        total_len = int(get_total_track_length(context, start_frame=start_frame))

        delete_tracks_by_names(context, final_tracks)
        scene.frame_current = current_frame
        space.clip_user.frame_current = current_frame

        return total_len

    def _test_rot_pair(self, context: Context, target_value: int, clip) -> Tuple[float, float]:
        scene = context.scene
        hz, vc = clip.size[0], clip.size[1]
        ratio = (hz / vc) if vc > 0 else 1.0
        best_x = best_y = 1.0
        min_value = self._min_threshold
        current_target = max(target_value, 0)

        for factor in self._reduction_factors:
            current_value = 1.0
            while current_value > min_value:
                current_value *= factor
                set_scene_props(scene, kaiserlich_rot_thresh_x=current_value, kaiserlich_rot_thresh_y=current_value * ratio)
                length = self._track_and_measure(context)
                if length >= current_target:
                    best_x = current_value
                    best_y = current_value * ratio
                    current_target = length
                    break

        return best_x, best_y

    def _test_single_threshold(self, context: Context, prop_name: str, target_value: int, freeze_others: Optional[Dict[str, float]] = None) -> float:
        scene = context.scene
        best_value = 1.0
        min_value = self._min_threshold
        current_target = max(target_value, 0)

        for factor in self._reduction_factors:
            current_value = 1.0
            while current_value > min_value:
                current_value *= factor
                if freeze_others:
                    set_scene_props(scene, **freeze_others)
                set_scene_props(scene, **{prop_name: current_value})
                length = self._track_and_measure(context)
                if length >= current_target:
                    best_value = current_value
                    current_target = length
                    break

        return best_value

    def _test_rot_scale_pair(self, context: Context, target_value: int) -> Tuple[float, float]:
        rot = self._test_single_threshold(context, 'kaiserlich_rot_scale_thresh_rot', target_value,
                                          freeze_others={'kaiserlich_rot_scale_thresh_scale': 0.0})
        scale = self._test_single_threshold(context, 'kaiserlich_rot_scale_thresh_scale', target_value,
                                            freeze_others={'kaiserlich_rot_scale_thresh_rot': 0.0})
        return rot, scale

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)
