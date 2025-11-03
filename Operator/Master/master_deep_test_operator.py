# Operator/Master/master_shorttest_operator.py
import bpy
import time
import math
from typing import Optional, List, Dict, Any, Tuple, Set, Deque
from collections import deque
from dataclasses import dataclass, field

# ---- Helper-Importe ---------------------------------------------------------
from ...Helper.util_clip import get_active_clip
from ...Helper.scene import get_end_frame
from ...Helper.reset_helper import reset_all_thresholds
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.newmarker import classify_markers
from ...Helper.find_clip_editor_area import find_clip_editor_area
from ...Helper.snapshot import snapshot_active_markers
from ...Helper.detect import detect_features
from ...Helper.cleaneup import cleanup_new_markers
from ...Helper.delete import delete_tracks_by_names
from ...Helper.track_length_helper import get_total_track_length
from ...Helper.selection_helper import collect_selected_track_names
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.track_markers_helper import track_markers_with_override
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.util_scene import set_scene_props
from ...Helper.init_detect_state import init_detect_state
from ...Helper.filter_and_delete_tracks import filter_and_delete_tracks


# ----------------------------------------------------------------------------
# Scene Keys
# ----------------------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"


# ----------------------------------------------------------------------------
# State Class
# ----------------------------------------------------------------------------
@dataclass
class _AutoCalibState:
    initialized: bool = False
    done: bool = False
    step: int = 0
    notes: Deque[str] = field(default_factory=lambda: deque(maxlen=200))

    did_reset_thresholds: bool = False
    did_detect_adapt: bool = False
    detect_adapt_done_confirmed: bool = False
    did_track_cycle: bool = False

    track_active: bool = False
    track_window: Optional[bpy.types.Window] = None
    track_area: Optional[bpy.types.Area] = None
    track_region: Optional[bpy.types.Region] = None
    track_space: Optional[bpy.types.Space] = None
    track_names: List[str] = field(default_factory=list)
    track_original_selected: List[str] = field(default_factory=list)
    track_frame_current: int = 0
    track_frame_end: int = 0
    track_start_frame: int = 0

    baseline_track_names: List[str] = field(default_factory=list)
    created_track_names: List[str] = field(default_factory=list)

    track_cycles_done: int = 0
    second_cycle: bool = False
    third_cycle: bool = False
    fourth_cycle: bool = False
    fifth_cycle: bool = False
    cycle_thresholds: Dict[int, Dict[str, float]] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Operator
# ----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_master_shorttest_operator(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.master_shorttest_operator"
    bl_label = "Kaiserlich Tracker — Auto Calibrate"
    bl_options = {'REGISTER', 'UNDO'}

    _timer: Optional[Any] = None
    _state: _AutoCalibState

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._state = _AutoCalibState()
        try:
            self._state.user_original_frame = int(context.scene.frame_current)
        except Exception:
            self._state.user_original_frame = None
        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}
        try:
            self._deselect_all_tracks(context)
        except Exception:
            pass
        self._state.notes.append("Init OK (modal).")
        return {'RUNNING_MODAL'}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == 'ESC':
            return self._teardown(context, cancelled=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if not self._state.initialized:
            self._state.initialized = True
            return {'RUNNING_MODAL'}

        if not self._state.did_reset_thresholds:
            try:
                reset_all_thresholds(context, active_props=[])
            except Exception:
                pass
            self._state.did_reset_thresholds = True
            return {'RUNNING_MODAL'}

        if not self._state.did_detect_adapt:
            try:
                self._detect_adapt_inline(context)
            except Exception:
                self._state.detect_adapt_done_confirmed = True
            self._state.did_detect_adapt = True
            return {'RUNNING_MODAL'}

        if self._state.did_detect_adapt and not self._state.detect_adapt_done_confirmed:
            return {'RUNNING_MODAL'}

        if self._state.detect_adapt_done_confirmed:
            if not self._state.track_active and not self._state.did_track_cycle:
                try:
                    self._track_cycle_start(context)
                except Exception:
                    self._state.did_track_cycle = True
                    return {'RUNNING_MODAL'}
                return {'RUNNING_MODAL'}

            if self._state.track_active:
                still_running = self._track_cycle_tick(context)
                if not still_running:
                    self._track_cycle_finish(context)
                    self._state.track_active = False
                    self._state.track_cycles_done += 1
                    self._state.did_track_cycle = True
                    return {'RUNNING_MODAL'}
                return {'RUNNING_MODAL'}

        if not self._state.done and self._state.did_track_cycle:
            if not self._state.second_cycle:
                try:
                    set_scene_props(context.scene, kaiserlich_rot_thresh_x=0.00001, kaiserlich_rot_thresh_y=0.00001)
                except Exception:
                    pass
                self._state.second_cycle = True
                self._state.cycle_thresholds[2] = {
                    'kaiserlich_rot_thresh_x': 0.00001,
                    'kaiserlich_rot_thresh_y': 0.00001,
                }
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            if self._state.second_cycle and not self._state.third_cycle:
                try:
                    reset_all_thresholds(context, active_props=[])
                    set_scene_props(context.scene, kaiserlich_scale_thresh_min=0.00001, kaiserlich_scale_thresh_max=0.00001)
                except Exception:
                    pass
                self._state.third_cycle = True
                self._state.cycle_thresholds[3] = {
                    'kaiserlich_scale_thresh_min': 0.00001,
                    'kaiserlich_scale_thresh_max': 0.00001,
                }
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            if self._state.third_cycle and not getattr(self._state, 'fourth_cycle', False):
                try:
                    reset_all_thresholds(context, active_props=[])
                    set_scene_props(context.scene, kaiserlich_rot_scale_thresh_rot=0.00001, kaiserlich_rot_scale_thresh_scale=0.00001)
                except Exception:
                    pass
                self._state.fourth_cycle = True
                self._state.cycle_thresholds[4] = {
                    'kaiserlich_rot_scale_thresh_rot': 0.00001,
                    'kaiserlich_rot_scale_thresh_scale': 0.00001,
                }
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            if getattr(self._state, 'fourth_cycle', False) and not getattr(self._state, 'fifth_cycle', False):
                try:
                    reset_all_thresholds(context, active_props=[])
                    set_scene_props(context.scene, kaiserlich_perspective_thresh=0.00001)
                except Exception:
                    pass
                self._state.fifth_cycle = True
                self._state.cycle_thresholds[5] = {'kaiserlich_perspective_thresh': 0.00001}
                self._state.did_detect_adapt = False
                self._state.detect_adapt_done_confirmed = False
                self._state.did_track_cycle = False
                return {'RUNNING_MODAL'}

            if self._state.second_cycle and self._state.third_cycle and getattr(self._state, 'fourth_cycle', False) and getattr(self._state, 'fifth_cycle', False):
                try:
                    scene = context.scene
                    baseline_len = int(scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0))
                    step_map = {
                        2: SCENE_TOTAL_TRACK_LEN_STEP1,
                        3: SCENE_TOTAL_TRACK_LEN_STEP2,
                        4: SCENE_TOTAL_TRACK_LEN_STEP3,
                        5: SCENE_TOTAL_TRACK_LEN_STEP4,
                    }
                    for key in step_map.values():
                        if key in scene:
                            del scene[key]
                    best_thresholds: Dict[str, float] = {}
                    for cycle_num, thresh_dict in self._state.cycle_thresholds.items():
                        step_key = step_map.get(cycle_num)
                        if not step_key:
                            continue
                        length_key = f"kaiserlich_len_cycle_{cycle_num}"
                        cycle_len = int(scene.get(length_key, 0))
                        if cycle_len > baseline_len:
                            scene[step_key] = cycle_len
                            best_thresholds.update(thresh_dict)
                    scene["kaiserlich_best_thresholds"] = best_thresholds
                except Exception:
                    pass
                try:
                    reset_all_thresholds(context, active_props=[])
                except Exception:
                    pass
                self._state.done = True
                return self._teardown(context, cancelled=False)
            self._state.done = True
            return self._teardown(context, cancelled=False)
        return {'RUNNING_MODAL'}

    def _deselect_all_tracks(self, context: bpy.types.Context) -> int:
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        if not tracking or not getattr(tracking, "tracks", None):
            return 0
        changed = 0
        for tr in tracking.tracks:
            if getattr(tr, "select", False):
                tr.select = False
                changed += 1
        return changed

    # --- (Restliche Methoden unverändert, aber ohne print-Ausgaben) ---
