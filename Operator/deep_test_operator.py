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

# ---- Szenen-Keys ------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"


class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    """Kaiserlich Tracker — Deep Threshold Test"""
    bl_idname = "kaiserlich_tracker.deep_test"
    bl_label = "Kaiserlich Tracker — Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    # Reduktionsstufen
    _reduction_factors = [0.95, 0.50, 0.20, 0.10, 0.05, 0.02, 0.01]
    _min_threshold = 0.00001

    # ----------------------------------------------------------------------
    # Haupt-Ablauf
    # ----------------------------------------------------------------------
    def execute(self, context: Context):
        scene = context.scene
        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        print("\n[Kaiserlich Tracker][DeepTest] Starte Deep-Threshold-Test …")

        # Baseline bestimmen
        base_length = self._track_and_measure(context)
        scene[SCENE_TOTAL_TRACK_LEN_BASE] = base_length
        print(f"[Kaiserlich Tracker][DeepTest] Baseline-Länge = {base_length}")

        # Zielwerte laden
        target_step1 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP1, 0))
        target_step2 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP2, 0))
        target_step3 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP3, 0))
        target_step4 = int(scene.get(SCENE_TOTAL_TRACK_LEN_STEP4, 0))
        print(f"[Kaiserlich Tracker][DeepTest] Zielwerte: "
              f"RotXY={target_step1}, Scale={target_step2}, RotScale={target_step3}, Persp={target_step4}")

        results: Dict[str, float] = {}

        # Test 1 – Rotation (X/Y)
        print("[Kaiserlich Tracker][DeepTest] → Test Rotations-Threshold (X/Y)")
        rot_x, rot_y = self._test_rot_pair(context, target_step1, clip)
        results['kaiserlich_rot_thresh_x'] = rot_x
        results['kaiserlich_rot_thresh_y'] = rot_y
        print(f"[Kaiserlich Tracker][DeepTest] ✅ RotXY fertig: x={rot_x:.5f}, y={rot_y:.5f}")

        # Test 2 – Skalierung (Min/Max)
        print("[Kaiserlich Tracker][DeepTest] → Test Scale-Min")
        scale_min = self._test_single_threshold(context, 'kaiserlich_scale_thresh_min', target_step2,
                                                freeze_others={'kaiserlich_scale_thresh_max': 1.0})
        print(f"[Kaiserlich Tracker][DeepTest] ✅ Scale-Min = {scale_min:.5f}")

        print("[Kaiserlich Tracker][DeepTest] → Test Scale-Max")
        scale_max = self._test_single_threshold(context, 'kaiserlich_scale_thresh_max', target_step2,
                                                freeze_others={'kaiserlich_scale_thresh_min': 1.0})
        print(f"[Kaiserlich Tracker][DeepTest] ✅ Scale-Max = {scale_max:.5f}")
        results['kaiserlich_scale_thresh_min'] = scale_min
        results['kaiserlich_scale_thresh_max'] = scale_max

        # Test 3 – Rot+Scale-Paar
        print("[Kaiserlich Tracker][DeepTest] → Test Rot/Scale-Paar")
        rot_scale_rot, rot_scale_scale = self._test_rot_scale_pair(context, target_step3)
        results['kaiserlich_rot_scale_thresh_rot'] = rot_scale_rot
        results['kaiserlich_rot_scale_thresh_scale'] = rot_scale_scale
        print(f"[Kaiserlich Tracker][DeepTest] ✅ RotScale fertig: rot={rot_scale_rot:.5f}, scale={rot_scale_scale:.5f}")

        # Test 4 – Perspektive
        print("[Kaiserlich Tracker][DeepTest] → Test Perspective")
        perspective = self._test_single_threshold(context, 'kaiserlich_perspective_thresh',
                                                  target_step4, freeze_others=results)
        results['kaiserlich_perspective_thresh'] = perspective
        print(f"[Kaiserlich Tracker][DeepTest] ✅ Perspective = {perspective:.5f}")

        # Ergebnis in Szene schreiben
        set_scene_props(scene, **results)
        print(f"[Kaiserlich Tracker][DeepTest] 🎯 Ergebnis: {results}")

        self.report({'INFO'}, "Deep Test abgeschlossen.")
        return {'FINISHED'}

    # ----------------------------------------------------------------------
    # Helper – Track & Measure
    # ----------------------------------------------------------------------
    def _track_and_measure(self, context: Context) -> int:
        scene = context.scene
        clip = get_active_clip(context)
        if clip is None:
            print("[DeepTest] ❌ Kein Clip aktiv.")
            return 0

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            print("[DeepTest] ❌ Kein Tracking-Objekt gefunden.")
            return 0

        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            print("[DeepTest] ❌ Kein CLIP_EDITOR-Kontext gefunden.")
            return 0

        start_frame = scene.frame_start
        current_frame = scene.frame_current
        scene.frame_current = start_frame
        try:
            space.clip_user.frame_current = start_frame
        except Exception:
            pass

        print(f"[DeepTest] Snapshot vor Detect (Frame {start_frame}) …")
        pre_snapshot = snapshot_active_markers(context)
        print(f"[DeepTest] Marker vorher: {len(pre_snapshot)}")

        try:
            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                bpy.ops.clip.detect_features(
                    placement='FRAME',
                    margin=100,
                    threshold=0.001,
                    min_distance=50
                )
        except Exception as e:
            print(f"[DeepTest] ⚠️ Detect-Fehler: {e}")

        post_snapshot = snapshot_active_markers(context)
        _, new_markers = classify_markers(pre_snapshot, post_snapshot)
        new_tracks = [m['track'] for m in new_markers]
        print(f"[DeepTest] Neue Marker: {len(new_markers)} → {new_tracks[:5]}")

        for tr in tracking.tracks:
            try:
                tr.select = True
                tr.mute = False
            except Exception:
                pass

        track_markers_with_override(window, area, region, space, backwards=False, sequence=True)
        total_len = int(get_total_track_length(context, start_frame=start_frame))
        print(f"[DeepTest] Gesamt-Track-Länge = {total_len}")

        if new_tracks:
            delete_tracks_by_names(context, new_tracks)
            print(f"[DeepTest] Cleanup: {len(new_tracks)} neue Tracks gelöscht.")

        scene.frame_current = current_frame
        try:
            space.clip_user.frame_current = current_frame
        except Exception:
            pass

        return total_len

    # ----------------------------------------------------------------------
    # Helper – Test Rotations-Thresholds
    # ----------------------------------------------------------------------
    def _test_rot_pair(self, context: Context, target_value: int, clip) -> Tuple[float, float]:
        scene = context.scene
        hz, vc = clip.size[0], clip.size[1]
        ratio = (hz / vc) if vc > 0 else 1.0

        start_value = 1.0
        min_value = self._min_threshold
        best_x = best_y = start_value
        threshold_min_found = min_value
        current_target = max(int(target_value), 0)

        print(f"[DeepTest] Rot-Pair-Start | ratio={ratio:.4f}, Ziel={current_target}")

        for factor in self._reduction_factors:
            current_value = start_value
            print(f"[DeepTest] Faktor-Stufe {factor}")
            while True:
                current_value *= factor
                if current_value < min_value:
                    break

                set_scene_props(scene,
                                kaiserlich_rot_thresh_x=current_value,
                                kaiserlich_rot_thresh_y=current_value * ratio)
                length = self._track_and_measure(context)
                print(f"[DeepTest] → Wert {current_value:.5f} → Länge {length}")

                if length >= current_target:
                    threshold_min_found = current_value
                    best_x = current_value
                    best_y = current_value * ratio
                    current_target = max(current_target, length)
                    print(f"[DeepTest] ✅ Verbesserung: Länge={length}, "
                          f"X={best_x:.5f}, Y={best_y:.5f}")
                    break

                if current_value <= threshold_min_found:
                    break

            set_scene_props(scene, kaiserlich_rot_thresh_x=start_value,
                            kaiserlich_rot_thresh_y=start_value)

        return best_x, best_y

    # ----------------------------------------------------------------------
    # Helper – Test einzelner Threshold
    # ----------------------------------------------------------------------
    def _test_single_threshold(self, context: Context, prop_name: str,
                               target_value: int,
                               freeze_others: Optional[Dict[str, float]] = None) -> float:
        scene = context.scene
        start_value = 1.0
        min_value = self._min_threshold
        best_value = start_value
        threshold_min_found = min_value
        current_target = max(int(target_value), 0)

        print(f"[DeepTest] Test-Start für {prop_name} | Ziel={current_target}")

        for factor in self._reduction_factors:
            current_value = start_value
            print(f"[DeepTest] Faktor-Stufe {factor}")
            while True:
                current_value *= factor
                if current_value < min_value:
                    break

                if freeze_others:
                    set_scene_props(scene, **freeze_others)
                set_scene_props(scene, **{prop_name: current_value})

                length = self._track_and_measure(context)
                print(f"[DeepTest] {prop_name}={current_value:.5f} → Länge={length}")

                if length >= current_target:
                    threshold_min_found = current_value
                    best_value = current_value
                    current_target = max(current_target, length)
                    print(f"[DeepTest] ✅ Verbesserung: {prop_name}={best_value:.5f}, Länge={length}")
                    break

                if current_value <= threshold_min_found:
                    break

            if freeze_others:
                set_scene_props(scene, **freeze_others)
            set_scene_props(scene, **{prop_name: start_value})

        return best_value

    # ----------------------------------------------------------------------
    # Helper – Test Rot/Scale-Paar
    # ----------------------------------------------------------------------
    def _test_rot_scale_pair(self, context: Context, target_value: int) -> Tuple[float, float]:
        print("[DeepTest] Test RotScale-Paar startet …")
        rot_value = self._test_single_threshold(
            context,
            prop_name='kaiserlich_rot_scale_thresh_rot',
            target_value=target_value,
            freeze_others={'kaiserlich_rot_scale_thresh_scale': 0.0}
        )
        print(f"[DeepTest] RotScale-Rot={rot_value:.5f}")

        scale_value = self._test_single_threshold(
            context,
            prop_name='kaiserlich_rot_scale_thresh_scale',
            target_value=target_value,
            freeze_others={'kaiserlich_rot_scale_thresh_rot': 0.0}
        )
        print(f"[DeepTest] RotScale-Scale={scale_value:.5f}")
        return rot_value, scale_value


# Registrierung ---------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)
