# Operator/Master/master_deep_test_operator.py
import bpy
from bpy.types import Operator, Context
from dataclasses import dataclass, field
from typing import Set

from ...Helper.snapshot import snapshot_active_markers
from ...Helper.detect_adapt_helper import run_detect_adapt
from ...Helper.util_clip import get_active_clip
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.track_length_helper import get_total_track_length
from ...Helper.delete import delete_tracks_by_names
from ...Helper.get_clip_context import get_clip_context


@dataclass
class DeepTestState:
    """Encapsulates all runtime data of the Deep Test process."""
    counter: int = 0
    stop_flag: bool = False
    
    base_value: float = 0.0
    reference_value: float = 0.0
    start: float = 0.0
    lower_limit: float = 0.0
    step: float = 0.0
    next_val: float = 0.0

    old_tracks: Set[str] = field(default_factory=set)
    new_tracks: Set[str] = field(default_factory=set)
    all_tracks: Set[str] = field(default_factory=set)


class KAISERLICHTRACKER_OT_master_deep_test_operator(Operator):
    bl_idname = "kaiserlichtracker.master_deep_test_operator"
    bl_label = "Kaiserlich Tracker: Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        self.state = DeepTestState()
        self.state.next_val = 0.0
        self.state.stop_flag = False

        while True:
            self._set_threshold(context)

            # Main loop through all threshold steps
            while not self.state.stop_flag:
                self._set_step_threshold(context)
                if self.state.stop_flag:
                    break  # single valid exit point for the process

                # --- Tracking test cycle ---
                self.state.next_val = 1.0
                self._set_step_threshold(context)
                self._track(context)

                self.state.base_value = self.state.reference_value

                self.state.start = self.state.next_val
                self.state.next_val = 0.00001
                self._set_step_threshold(context)
                self.state.lower_limit = self.state.next_val
                self._track(context)

                if self.state.reference_value <= self.state.base_value:
                    self.state.step = self.state.step + 1
                    continue

                self.state.step = abs(self.state.start - self.state.lower_limit) / 2.0
                self.state.next_val = self.state.next_val + self.state.step
                self._set_step_threshold(context)
                self._track(context)

                if self.state.reference_value < self.state.base_value:
                    self._minus_thresh(context)
                else:
                    if self.state.reference_value > self.state.base_value:
                        self.state.base_value = self.state.reference_value
                        self._plus_thresh(context)
                    else:
                        self._plus_thresh(context)

        print("[DeepTest] ✅ All steps completed — process finished.")
        return {'FINISHED'}

    
    def _set_threshold(self, context: Context) -> None:
        scene = context.scene
        # Baseline reset: all threshold parameters set to 1.0
        scene.kaiserlich_rot_thresh_x = 1.0
        scene.kaiserlich_rot_thresh_y = 1.0
        scene.kaiserlich_scale_thresh_min = 1.0
        scene.kaiserlich_scale_thresh_max = 1.0
        scene.kaiserlich_rot_scale_thresh_rot = 1.0
        scene.kaiserlich_rot_scale_thresh_scale = 1.0
        scene.kaiserlich_perspective_thresh = 1.0

    def _set_step_threshold(self, context: Context) -> None:
        clip = get_active_clip(context)
        scene = context.scene

        if self.state.step == 0:
            # rot_xy
            if clip:
                width, height = clip.size
                # Couple Y to aspect ratio, capped at 1.0
                y_val = min(1.0, self.state.next_val * (height / width if width else 1.0))
                scene.kaiserlich_rot_thresh_x = float(self.state.next_val)
                scene.kaiserlich_rot_thresh_y = float(y_val)
            return

        elif self.state.step == 1:
            # scale_min/max
            scene.kaiserlich_scale_thresh_min = float(self.state.next_val)
            scene.kaiserlich_scale_thresh_max = float(min(1.0, self.state.next_val * 1.1))
            return

        elif self.state.step == 2:
            # rot_scale: rotation
            scene.kaiserlich_rot_scale_thresh_rot = float(self.state.next_val)
            scene.kaiserlich_rot_scale_thresh_scale = 0.0
            return

        elif self.state.step == 3:
            # rot_scale: scale
            scene.kaiserlich_rot_scale_thresh_rot = 0.0
            scene.kaiserlich_rot_scale_thresh_scale = float(self.state.next_val)
            return

        elif self.state.step == 4:
            # perspective
            scene.kaiserlich_perspective_thresh = float(self.state.next_val)
            return

        elif self.state.step >= 5:
            self.state.stop_flag = True
            return

def _track(self, context: Context):
    clip = get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        print("[DeepTest] ❌ Kein aktiver Clip.")
        return

    old_data = snapshot_active_markers(context)
    try:
        run_detect_adapt(context)
    except Exception as ex:
        print(f"[DeepTest] ❌ DetectAdapt-Fehler: {ex!r}")
        return

    import time
    time.sleep(0.1)
    bpy.context.view_layer.update()

    all_data = snapshot_active_markers(context)
    old = {d["track"] for d in old_data if "track" in d}
    all_ = {d["track"] for d in all_data if "track" in d}
    self.state.new_tracks = all_ - old
    print(f"[DeepTest] Neue Tracks: {len(self.state.new_tracks)}")

    self._track_forward_with_limits(context)

    scene = context.scene
    self.state.reference_value = get_total_track_length(
        context,
        start_frame=scene.frame_start,
        include_names=self.state.new_tracks
    )
    print(f"[DeepTest] Track-Länge: {self.state.reference_value}")

    if self.state.new_tracks:
        delete_tracks_by_names(context, track_names=self.state.new_tracks)


    def _plus_thresh(self, context: Context) -> None:
        while True:
            self.state.lower_limit = self.state.next_val
            step = abs(self.state.start - self.state.lower_limit) / 2.0
            if step > 0.0001:
                self.state.next_val = self.state.next_val + step
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
                self.state.step = self.state.step + 1
                # start next step
                return

    def _minus_thresh(self, context: Context) -> None:
        while True:
            self.state.start = self.state.next_val
            step = abs(self.state.start - self.state.lower_limit) / 2.0
            if step > 0.0001:
                self.state.next_val = self.state.next_val - step
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
                self.state.step = self.state.step + 1
                # start next step
                return

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
        if log:
            print("[TrackForward] ❌ Kein aktiver Clip.")
        return 0

    end_frame = int(scene.frame_end)
    current_frame = int(scene.frame_current)
    original_frame = current_frame
    remaining = end_frame - current_frame
    if remaining < min_distance_to_end:
        new_start = max(scene.frame_start, end_frame - min_distance_to_end)
        reset_to_frame(context, new_start)
        scene.frame_current = new_start
        current_frame = new_start

    tracking = clip.tracking
    active_tracks = [t.name for t in tracking.tracks if getattr(t, "select", False)]
    if not active_tracks:
        if log:
            print("[TrackForward] ⚠️ Keine Tracks selektiert.")
        return 0

    ctx_override = get_clip_context()
    if not ctx_override:
        if log:
            print("[TrackForward] ❌ Kein gültiger Kontext.")
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
        with bpy.context.temp_override(**ctx_override):
            result = bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False)
        if 'CANCELLED' in str(result):
            break
        frames_tracked += 1
        current_frame += 1
        scene.frame_current = current_frame

    total_len = get_total_track_length(context, start_frame=scene.frame_start, include_names=active_tracks)
    if log:
        print(f"[TrackForward] ✅ {frames_tracked} Frames, Länge {total_len}")

    try:
        reset_to_frame(context, original_frame)
        scene.frame_current = original_frame
    except Exception:
        pass

    return frames_tracked

