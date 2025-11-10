# =================================================================================================
# File: Operator/Master/master_deep_test_operator.py
# -------------------------------------------------------------------------------------------------
# Kaiserlich Tracker – Deep Test Operator
# -------------------------------------------------------------------------------------------------
# Purpose:
# Performs an automated, incremental threshold calibration for the Kaiserlich Tracker.
# Evaluates and refines detection thresholds across multiple categories
# (rotation, scale, rotation-scale, and perspective) through iterative optimization loops.
#
# The operator runs as a modal, non-blocking process via timer events,
# allowing Blender’s UI to remain responsive during calibration.
#
# Once convergence is reached or all test phases are completed,
# control is automatically passed to the "master_detect_adapt" operator.
# -------------------------------------------------------------------------------------------------

import bpy
from bpy.types import Operator, Context
from dataclasses import dataclass, field
from typing import Set
import time, math

# -------------------------------------------------------------------------------------------------
# Helper Imports
# -------------------------------------------------------------------------------------------------
from ...Helper.snapshot import snapshot_active_markers
from ...Helper.detect_adapt_helper import run_detect_adapt
from ...Helper.util_clip import get_active_clip
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.track_length_helper import get_total_track_length
from ...Helper.delete import delete_tracks_by_names
from ...Helper.get_clip_context import get_clip_context
from ...Helper.ui_progress import set_progress


# -------------------------------------------------------------------------------------------------
# Dataclass – Deep Test Runtime State
# -------------------------------------------------------------------------------------------------
@dataclass
class DeepTestState:
    counter: int = 0
    stop_flag: bool = False
    base_value: float = 0.0
    reference_value: float = 0.0
    start: float = 0.0
    lower_limit: float = 0.0
    step: float = 0.0
    next_val: float = 0.0
    converter: float = 0.0

    rot_thresh_x: float = 1.0
    rot_thresh_y: float = 1.0
    scale_thresh_min: float = 1.0
    scale_thresh_max: float = 1.0
    rot_scale_thresh_rot: float = 1.0
    rot_scale_thresh_scale: float = 1.0
    perspective_thresh: float = 1.0

    old_tracks: Set[str] = field(default_factory=set)
    new_tracks: Set[str] = field(default_factory=set)
    all_tracks: Set[str] = field(default_factory=set)

    phase: str = "INIT"
    substep: int = 0
    yield_flag: bool = False


# -------------------------------------------------------------------------------------------------
# Operator Class
# -------------------------------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_master_deep_test_operator(Operator):
    """Kaiserlich Tracker: Deep Test"""
    bl_idname = "kaiserlichtracker.master_deep_test_operator"
    bl_label = "Kaiserlich Tracker: Deep Test"
    bl_description = "Performs iterative threshold calibration for all categories"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None

    converter: bpy.props.FloatProperty(
        name="Converter",
        description="Intermediate progress calculation value",
        default=0.0,
        min=0.0,
        max=1.0
    )

    # ---------------------------------------------------------------------------------------------
    # Execute (Entry)
    # ---------------------------------------------------------------------------------------------
    def execute(self, context: Context):
        self.state = DeepTestState()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    # ---------------------------------------------------------------------------------------------
    # Modal Loop
    # ---------------------------------------------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            self._ui_progress(context)
            try:
                if self.state.stop_flag or self.state.phase == "DONE":
                    self._finalize(context)
                    self.cancel(context)
                    return {'FINISHED'}
                self._process_step_incremental(context)
            except Exception:
                self.cancel(context)
                return {'CANCELLED'}

        return {'PASS_THROUGH'}

    # ---------------------------------------------------------------------------------------------
    # Cancel / Timer Cleanup
    # ---------------------------------------------------------------------------------------------
    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

    # ---------------------------------------------------------------------------------------------
    # Incremental Step Processor
    # ---------------------------------------------------------------------------------------------
    def _process_step_incremental(self, context: Context):
        s = self.state

        if s.phase == "INIT":
            s.phase = "STEP_START"
            return

        if s.phase == "STEP_START":
            self._set_step_threshold(context)
            if s.stop_flag:
                return
            s.next_val = 1.0
            self._set_step_threshold(context)
            s.phase = "STEP_TEST_HIGH"
            return

        if s.phase == "STEP_TEST_HIGH":
            self._track(context)
            s.base_value = s.reference_value
            s.start = s.next_val
            s.next_val = 0.00001
            self._set_step_threshold(context)
            s.lower_limit = s.next_val
            s.phase = "STEP_TEST_LOW"
            return

        if s.phase == "STEP_TEST_LOW":
            self._track(context)
            if s.reference_value <= s.base_value:
                s.next_val = 1
                self._set_step_threshold(context)
                s.step += 1
                if s.step >= 5:
                    self._set_step_threshold(context)
                    s.phase = "DONE"
                    s.stop_flag = True
                else:
                    s.phase = "INIT"
                return
            s.base_value = s.reference_value
            s.converter = abs(s.start - s.lower_limit) / 2.0
            self.converter = s.converter
            s.next_val = s.next_val + s.converter
            self._set_step_threshold(context)
            s.phase = "STEP_MID"
            return

        if s.phase == "STEP_MID":
            self._track(context)
            if s.reference_value < s.base_value:
                s.phase = "ADJUST_MINUS"
            elif s.reference_value > s.base_value:
                s.base_value = s.reference_value
                s.phase = "ADJUST_PLUS"
            else:
                s.phase = "ADJUST_PLUS"
            return

        if s.phase == "ADJUST_PLUS":
            s.lower_limit = s.next_val
            conv = abs(s.start - s.lower_limit) / 2.0
            if conv > 0.00001:
                s.next_val = s.next_val + conv
                s.converter = conv
                self.converter = conv
                self._set_step_threshold(context)
                s.phase = "ADJUST_PLUS_TRACK"
            else:
                s.step += 1
                s.phase = "INIT" if s.step < 5 else "DONE"
                s.stop_flag = (s.phase == "DONE")
            return

        if s.phase == "ADJUST_PLUS_TRACK":
            self._track(context)
            if s.reference_value >= s.base_value:
                if s.reference_value > s.base_value:
                    s.base_value = s.reference_value
                    s.phase = "ADJUST_PLUS"
                else:
                    s.phase = "ADJUST_PLUS"
            else:
                s.phase = "ADJUST_MINUS"
            return

        if s.phase == "ADJUST_MINUS":
            s.start = s.next_val
            conv = abs(s.start - s.lower_limit) / 2.0
            if conv > 0.00001:
                s.next_val = s.next_val - conv
                s.converter = conv
                self.converter = conv
                self._set_step_threshold(context)
                s.phase = "ADJUST_MINUS_TRACK"
            else:
                s.step += 1
                if s.step >= 5:
                    self._set_step_threshold(context)
                    s.phase = "DONE"
                    s.stop_flag = True
                else:
                    s.phase = "INIT"
                return

        if s.phase == "ADJUST_MINUS_TRACK":
            self._track(context)
            if s.reference_value < s.base_value:
                s.phase = "ADJUST_MINUS"
            else:
                if s.reference_value > s.base_value:
                    s.base_value = s.reference_value
                    s.phase = "ADJUST_PLUS"
                else:
                    s.phase = "ADJUST_PLUS"
            return

        if s.phase == "DONE":
            self._finalize(context)
            return

    # ---------------------------------------------------------------------------------------------
    # Threshold Setting and Progress Calculation
    # ---------------------------------------------------------------------------------------------
    def _set_step_threshold(self, context: Context) -> None:
        clip = get_active_clip(context)
        scene = context.scene
        step = self.state.step
        val = self.state.next_val
        converter = self.state.converter

        vale = min(100.0, 100.0 - (((math.log10(max(0.00001, converter) * 100000.0) - 0.205) * 1.03) * 20.0))
        if vale < 100:
            total = max(0, min(100, (((step * 1.24) + 1) * 17) - ((100 - (vale - 1)) / 6)))
            scene.kaiserlich_progress_step = f"{int(total)}%"
        scene.kaiserlich_progress_title = f"{int(vale)}%"

        try:
            scene.kaiserlich_converter = converter
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()
        except Exception:
            pass

        # Step-specific threshold assignment
        if step == 0 and clip:
            width, height = clip.size
            y_val = min(1.0, val * (width / height if width else 1.0))
            scene.kaiserlich_rot_thresh_x = float(val)
            scene.kaiserlich_rot_thresh_y = float(y_val)
            self.state.rot_thresh_x = float(val)
            self.state.rot_thresh_y = float(y_val)
            scene.kaiserlich_scale_thresh_min = 1
            scene.kaiserlich_scale_thresh_max = 1
            scene.kaiserlich_rot_scale_thresh_rot = 1
            scene.kaiserlich_rot_scale_thresh_scale = 1
            scene.kaiserlich_perspective_thresh = 1
            return

        elif step == 1:
            scene.kaiserlich_rot_thresh_x = 1
            scene.kaiserlich_rot_thresh_y = 1
            scene.kaiserlich_scale_thresh_min = float(val)
            scene.kaiserlich_scale_thresh_max = float(min(1.0, val * 1.1))
            self.state.scale_thresh_min = float(val)
            self.state.scale_thresh_max = float(min(1.0, val * 1.1))
            scene.kaiserlich_rot_scale_thresh_rot = 1
            scene.kaiserlich_rot_scale_thresh_scale = 1
            scene.kaiserlich_perspective_thresh = 1
            return

        elif step == 2:
            scene.kaiserlich_rot_scale_thresh_rot = float(val)
            self.state.rot_scale_thresh_rot = float(val)
            return

        elif step == 3:
            scene.kaiserlich_rot_scale_thresh_scale = float(val)
            self.state.rot_scale_thresh_scale = float(val)
            return

        elif step == 4:
            scene.kaiserlich_perspective_thresh = float(val)
            self.state.perspective_thresh = float(val)
            return

        elif step >= 5:
            scene.kaiserlich_rot_thresh_x = self.state.rot_thresh_x
            scene.kaiserlich_rot_thresh_y = self.state.rot_thresh_y
            scene.kaiserlich_scale_thresh_min = self.state.scale_thresh_min
            scene.kaiserlich_scale_thresh_max = self.state.scale_thresh_max
            scene.kaiserlich_rot_scale_thresh_rot = self.state.rot_scale_thresh_rot
            scene.kaiserlich_rot_scale_thresh_scale = self.state.rot_scale_thresh_scale
            scene.kaiserlich_perspective_thresh = self.state.perspective_thresh
            self.state.stop_flag = True
            self.state.phase = "DONE"
            return

    # ---------------------------------------------------------------------------------------------
    # Tracking Procedure
    # ---------------------------------------------------------------------------------------------
    def _track(self, context: Context):
        clip = get_active_clip(context)
        if not clip:
            return
        scene = context.scene
        frame_playhead = int(scene.frame_current)
        frame_end = int(scene.frame_end)
        frame_max = max(scene.frame_start, frame_end - 50)
        restore_playhead = None

        if frame_playhead > frame_max:
            restore_playhead = frame_playhead
            reset_to_frame(context, frame_max)
            scene.frame_current = frame_max

        old_data = snapshot_active_markers(context)
        try:
            run_detect_adapt(context)
        except Exception:
            pass

        time.sleep(0.1)
        bpy.context.view_layer.update()

        all_data = snapshot_active_markers(context)
        old_names = {d["track"] for d in old_data if isinstance(d, dict) and "track" in d}
        all_names = {d["track"] for d in all_data if isinstance(d, dict) and "track" in d}

        self.state.old_tracks = old_names
        self.state.all_tracks = all_names
        self.state.new_tracks = all_names - old_names

        self._track_forward_with_limits(context)

        self.state.reference_value = get_total_track_length(
            context, start_frame=scene.frame_start, include_names=self.state.new_tracks
        )

        if self.state.new_tracks:
            delete_tracks_by_names(context, track_names=self.state.new_tracks)

        if restore_playhead is not None:
            reset_to_frame(context, restore_playhead)
            scene.frame_current = restore_playhead

    # ---------------------------------------------------------------------------------------------
    # Finalization / Handover
    # ---------------------------------------------------------------------------------------------
    def _finalize(self, context: Context):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()
        self.state.stop_flag = True
        self._invoke_master_detect_adapt(context)

    def _invoke_master_detect_adapt(self, context: Context) -> None:
        try:
            area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
            if not area:
                return
            override = context.copy()
            override['area'] = area
            override['region'] = next((r for r in area.regions if r.type == 'WINDOW'), None)
            with context.temp_override(**override):
                bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
        except Exception:
            pass

    # ---------------------------------------------------------------------------------------------
    # UI Refresh
    # ---------------------------------------------------------------------------------------------
    def _ui_progress(self, context: Context):
        try:
            for area in context.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()
        except Exception:
            pass

    # ---------------------------------------------------------------------------------------------
    # Internal Plus/Minus Recursive Loops (unchanged logic)
    # ---------------------------------------------------------------------------------------------
    def _plus_thresh(self, context: Context) -> None:
        while True:
            self.state.lower_limit = self.state.next_val
            converter = abs(self.state.start - self.state.lower_limit) / 2.0
            if converter > 0.00001:
                self.state.next_val = self.state.next_val + converter
                self._set_step_threshold(context)
                self._track(context)
                if self.state.reference_value >= self.state.base_value:
                    if self.state.reference_value > self.state.base_value:
                        self.state.base_value = self.state.reference_value
                        continue
                    else:
                        continue
                else:
                    self._minus_thresh(context)
            else:
                self.state.step += 1
                return

    def _minus_thresh(self, context: Context) -> None:
        while True:
            self.state.start = self.state.next_val
            converter = abs(self.state.start - self.state.lower_limit) / 2.0
            if converter > 0.00001:
                self.state.next_val = self.state.next_val - converter
                self._set_step_threshold(context)
                self._track(context)
                if self.state.reference_value < self.state.base_value:
                    continue
                else:
                    if self.state.reference_value > self.state.base_value:
                        self.state.base_value = self.state.reference_value
                        self._plus_thresh(context)
                    else:
                        self._plus_thresh(context)
            else:
                self.state.step += 1
                return

    # ---------------------------------------------------------------------------------------------
    # Tracking Forward (Limited Range)
    # ---------------------------------------------------------------------------------------------
    def _track_forward_with_limits(
        self,
        context: Context,
        *,
        max_frames: int = 50,
        min_distance_to_end: int = 50,
        log: bool = True
    ) -> int:
        scene = context.scene
        clip = get_active_clip(context)
        if not clip or not getattr(clip, "tracking", None):
            return 0

        end_frame = int(scene.frame_end)
        current_frame = int(scene.frame_current)
        original_frame = current_frame
        remaining = end_frame - current_frame

        if remaining < min_distance_to_end:
            new_start = max(scene.frame_start, end_frame - min_distance_to_end)
            reset_to_frame(context, new_start)
            scene.frame_current = new_start

        tracking = clip.tracking
        active_tracks = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        if not active_tracks:
            return 0

        ctx_override = get_clip_context()
        if not ctx_override:
            return 0

        frames_tracked = 0
        for _ in range(max_frames):
            if current_frame >= end_frame:
                break

            active_tracks, dropped = filter_active_tracks_at_frame(context, active_tracks, current_frame)
            if not active_tracks:
                break

            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception:
                pass

            current_frame += 1
            frames_tracked += 1

        return frames_tracked
