# Operator/deep_test_operator.py
import bpy
import time
import math
from typing import Optional, List, Dict, Any, Tuple, Set
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.util_clip import get_active_clip
from ..Helper.scene import get_end_frame
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.newmarker import classify_markers
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.util_scene import set_scene_props

# ---- Szenen-Keys ------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"

# ---- Reduktions-Stufen ------------------------------------------------------
REDUCTION_STEPS = [0.05, 0.5, 0.8, 0.9, 0.95, 0.98, 0.99]
MIN_THRESHOLD_VAL = 0.00001


class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    """Deep Threshold Test (Modal): führt pro Kategorie stufenweise Reduktion der Thresholds durch und testet jeweils."""
    bl_idname = "kaiserlich_tracker.deep_test_operator"
    bl_label = "Kaiserlich Tracker — Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    # Laufzeitvariablen -------------------------------------------------------
    _timer = None
    _scene: Optional[bpy.types.Scene] = None
    _clip: Optional[bpy.types.MovieClip] = None
    _window = None
    _area = None
    _region = None
    _space = None

    _hz: int = 0
    _vc: int = 0
    _ratio_xy: float = 1.0

    _ef_target: int = 25
    _tolerance: float = 0.0

    _start_frame: int = 1
    _end_frame: int = 1
    _current_frame: int = 1

    _phase: str = "init"
    _categories_queue: List[str] = []
    _current_category: Optional[str] = None

    _current_step_index: int = 0
    _base_value: float = 1.0
    _current_value: float = 1.0
    _current_goal: int = 0

    _detect_loop: int = 0
    _detect_loop_max: int = 8
    _pre_snapshot: List[Dict[str, Any]] = []
    _baseline_start_tracknames: Set[str] = set()
    _last_md: float = 100.0
    _processing_names: List[str] = []
    _final_new_tracks: List[str] = []

    _goal_map: Dict[str, int] = {}
    _best_thresholds: Dict[str, float] = {}

    # ------------------------------------------------------------------------
    def execute(self, context: Context):
        self._scene = context.scene
        self._clip = get_active_clip(context)
        if not self._clip:
            self.report({'ERROR'}, "Kein aktiver Clip gefunden.")
            return {'CANCELLED'}

        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            self.report({'ERROR'}, "Keine CLIP_EDITOR Area gefunden.")
            return {'CANCELLED'}

        self._hz, self._vc = self._clip.size
        self._ratio_xy = (self._hz / self._vc) if self._vc else 1.0
        self._ef_target = int(self._scene.kaiserlich_markers_per_frame)
        self._tolerance = max(1.0, self._ef_target * 0.10)
        self._start_frame = int(self._scene.frame_start)
        self._end_frame = int(get_end_frame(context))
        self._current_frame = max(self._start_frame, int(self._scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        self._scene.frame_current = self._current_frame

        # Zielwerte laden
        self._goal_map = {
            "rot_xy": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP1, 0)),
            "scale": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP2, 0)),
            "rot_scale": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP3, 0)),
            "perspective": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP4, 0))
        }

        self._categories_queue = [k for k, v in self._goal_map.items() if v > 0]
        if not self._categories_queue:
            self.report({'INFO'}, "Keine Zielwerte vorhanden – Test abgebrochen.")
            return {'CANCELLED'}

        print(f"[Kaiserlich Tracker][DeepTest] Start – Kategorien: {self._categories_queue}")
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._phase = "category_select"
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'ESC':
            return self._teardown(context, cancelled=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._phase == "category_select":
            if not self._categories_queue:
                return self._finish(context)
            self._current_category = self._categories_queue.pop(0)
            self._prepare_category(context)
            self._phase = "threshold_cycle"
            return {'RUNNING_MODAL'}

        if self._phase == "threshold_cycle":
            finished = self._process_threshold_cycle(context)
            if finished:
                if self._categories_queue:
                    self._phase = "category_select"
                    return {'RUNNING_MODAL'}
                else:
                    return self._finish(context)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    def _prepare_category(self, context):
        print(f"\n[DeepTest][Category] → {self._current_category}")
        self._base_value = 1.0
        self._current_step_index = 0
        self._current_goal = self._goal_map.get(self._current_category, 0)
        self._best_thresholds[self._current_category] = 1.0
        self._pre_snapshot = snapshot_active_markers(context)
        self._baseline_start_tracknames = {t.name for t in self._clip.tracking.tracks}

        # Reset Thresholds auf 1.0 für die Kategorie
        if self._current_category == "rot_xy":
            set_scene_props(self._scene, kaiserlich_rot_thresh_x=1.0, kaiserlich_rot_thresh_y=1.0)
        elif self._current_category == "scale":
            set_scene_props(self._scene, kaiserlich_scale_thresh_min=1.0, kaiserlich_scale_thresh_max=0.0)
        elif self._current_category == "rot_scale":
            set_scene_props(self._scene, kaiserlich_rot_scale_thresh_rot=1.0, kaiserlich_rot_scale_thresh_scale=0.0)
        elif self._current_category == "perspective":
            set_scene_props(self._scene, kaiserlich_perspective_thresh=1.0)

    # ------------------------------------------------------------------------
    def _process_threshold_cycle(self, context) -> bool:
        """Durchläuft die Threshold-Stufen sequentiell und prüft je Durchgang."""
        if self._current_step_index >= len(REDUCTION_STEPS):
            print(f"[DeepTest][{self._current_category}] Alle Reduktionsstufen abgeschlossen.")
            return True

        step_factor = REDUCTION_STEPS[self._current_step_index]
        next_val = max(MIN_THRESHOLD_VAL, self._base_value * step_factor)
        self._current_value = next_val

        # Thresholds setzen
        if self._current_category == "rot_xy":
            try:
                delta = (math.log10(1 * 1_000_000) - math.log10(next_val * 1_000_000))
                adj = pow((delta * (self._vc / self._hz)), 10) / 1_000_000
            except ValueError:
                adj = 0.0
            set_scene_props(self._scene,
                            kaiserlich_rot_thresh_x=next_val,
                            kaiserlich_rot_thresh_y=next_val + adj)
        elif self._current_category == "scale":
            set_scene_props(self._scene, kaiserlich_scale_thresh_min=next_val)
        elif self._current_category == "rot_scale":
            set_scene_props(self._scene, kaiserlich_rot_scale_thresh_rot=next_val,
                            kaiserlich_rot_scale_thresh_scale=0.0)
        elif self._current_category == "perspective":
            set_scene_props(self._scene, kaiserlich_perspective_thresh=next_val)

        print(f"[DeepTest][{self._current_category}] Test Step {self._current_step_index + 1}/{len(REDUCTION_STEPS)}: {next_val}")

        # Detect
        self._detect_adapt_cycle(context)

        # Track
        total_len = self._track_and_measure(context)
        baseline_len = int(self._scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0))
        print(f"[DeepTest][{self._current_category}] Ergebnis Track Length = {total_len}, Baseline = {baseline_len}")

        # Bewertung
        if total_len > self._current_goal:
            print(f"[DeepTest][{self._current_category}] ✅ Ziel verbessert: {total_len} > {self._current_goal}")
            self._best_thresholds[self._current_category] = self._current_value
            self._current_goal = total_len
        else:
            print(f"[DeepTest][{self._current_category}] Kein Zugewinn.")

        self._base_value = self._current_value
        self._current_step_index += 1
        reset_to_frame(context, self._start_frame)

        return False

    # ------------------------------------------------------------------------
    def _detect_adapt_cycle(self, context):
        """Führt einen kurzen Detect/Cleanup-Zyklus aus."""
        detect_features(context, placement='FRAME', margin=100, threshold=0.0001, min_distance=50)
        post_snapshot = snapshot_active_markers(context)
        alte, neue = classify_markers(self._pre_snapshot, post_snapshot)
        cleanup_new_markers(context, alte, neue, pz=50, hz=self._hz, vc=self._vc)
        self._final_new_tracks = [m['track'] for m in neue]
        for trk in getattr(self._clip.tracking, "tracks", []):
            trk.select = (trk.name in self._final_new_tracks)

    def _track_and_measure(self, context) -> int:
        """Trackt einmal komplett vorwärts und misst Gesamtlänge."""
        window, area, region, space = self._window, self._area, self._region, self._space
        scene = self._scene
        scene.frame_current = self._start_frame
        space.clip_user.frame_current = self._start_frame
        while scene.frame_current < self._end_frame:
            track_markers_with_override(window, area, region, space, backwards=False, sequence=False)
            scene.frame_current += 1
            space.clip_user.frame_current = scene.frame_current
        total_len = int(get_total_track_length(context, start_frame=self._start_frame))
        delete_tracks_by_names(context, self._final_new_tracks)
        return total_len

    # ------------------------------------------------------------------------
    def _finish(self, context):
        print("\n[DeepTest] ✅ Abschluss – beste Thresholds:")
        for k, v in self._best_thresholds.items():
            print(f"  {k}: {v:.6f}")
        context.scene["kaiserlich_best_thresholds"] = self._best_thresholds
        return self._teardown(context, cancelled=False)

    def _teardown(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        msg = "Deep Test abgebrochen." if cancelled else "Deep Test abgeschlossen."
        try:
            self.report({'INFO'}, msg)
        except:
            print(msg)
        return {'CANCELLED' if cancelled else 'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)
