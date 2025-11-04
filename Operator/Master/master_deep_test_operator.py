# Operator/Master/master_deep_test_operator.py
import bpy
from bpy.types import Operator, Context
from dataclasses import dataclass, field
from typing import Set
import time

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
    track_flag: bool = False
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
                while not self.state.track_flag:
                    time.sleep(0.1)
                    self._refresh_clip_editor_viewer(context)
                    if self.state.track_flag:
                        if self.state.reference_value <= self.state.base_value:
                            self.state.step += 1
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

    def _refresh_clip_editor_viewer(self, context: Context):
        # Alle Fenster und Bereiche iterieren
        for window in bpy.context.window_manager.windows:
            screen = window.screen
            for area in screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            region.tag_redraw()
    
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
        # Vorher/Nachher-Snapshot
        old_data = snapshot_active_markers(context)
        run_detect_adapt(context)
        all_data = snapshot_active_markers(context)
    
        # Extrahiere nur Namen (stringbasiert)
        old_names = {d["name"] for d in old_data if isinstance(d, dict) and "name" in d}
        all_names = {d["name"] for d in all_data if isinstance(d, dict) and "name" in d}
    
        self.state.alte_tracker = old_names
        self.state.alle_tracker = all_names
        self.state.neu_tracker = all_names - old_names
        # Forward tracking with limits
        self._track_forward_with_limits(context)

        # Compute metric
        scene = context.scene
        self.state.reference_value = get_total_track_length(
            context,
            start_frame=scene.frame_start,
            include_names=self.state.new_tracks
        )

        # Cleanup: delete only newly created tracks
        if self.state.new_tracks:
            delete_tracks_by_names(context, include_names=self.state.new_tracks)
            self.state.track_flag = True

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
                self.state.step += 1
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
                self.state.step += 1
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
        """
        Performs limited forward tracking starting from the current playhead position.

        Returns:
            Total number of tracked frames (0 if aborted)
        """
        scene = context.scene
        clip = get_active_clip(context)
        if not clip or not getattr(clip, "tracking", None):
            if log:
                print("[TrackForward] ❌ No active clip found.")
            return 0

        end_frame = int(scene.frame_end)
        current_frame = int(scene.frame_current)
        original_frame = current_frame
        remaining = end_frame - current_frame

        # --- Validate or adjust start position ---
        if remaining < min_distance_to_end:
            new_start = max(scene.frame_start, end_frame - min_distance_to_end)
            if log:
                print(f"[TrackForward] ⚠️ Less than {min_distance_to_end} frames remaining "
                      f"({remaining}) → Starting at frame {new_start}.")
            reset_to_frame(context, new_start)
            scene.frame_current = new_start
            current_frame = new_start
        else:
            if log:
                print(f"[TrackForward] ✅ Sufficient frames remaining ({remaining}). Starting at {current_frame}.")

        # --- Collect active (selected) tracks ---
        tracking = clip.tracking
        active_tracks = [t.name for t in tracking.tracks if t.select]
        if not active_tracks:
            if log:
                print("[TrackForward] ⚠️ No selected tracks found for tracking.")
            return 0

        # --- Get context override ---
        ctx_override = get_clip_context()
        if not ctx_override:
            print("[TrackForward] ❌ No valid clip context available – aborting.")
            return 0

        # --- Tracking loop ---
        frames_tracked = 0
        for _ in range(max_frames):
            if current_frame >= end_frame:
                if log:
                    print("[TrackForward] ⏹️ Scene end reached.")
                break

            active_tracks, _dropped = filter_active_tracks_at_frame(context, active_tracks, current_frame)
            if not active_tracks:
                if log:
                    print("[TrackForward] ⏹️ No active tracks left – stopping tracking.")
                break

            try:
                # minor parameter adjustments before tracking, if configured
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception as ex:
                if log:
                    print(f"[TrackForward] ⚠️ Formula error: {ex!r}")

            # --- Execute tracking via override ---
            with bpy.context.temp_override(**ctx_override):
                result = bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False)
            if 'CANCELLED' in str(result):
                if log:
                    print("[TrackForward] ⚠️ Tracking failed – aborting.")
                break

            frames_tracked += 1
            current_frame += 1
            scene.frame_current = current_frame

            # Best-effort UI update
            try:
                context.space_data.clip_user.frame_current = current_frame
            except Exception:
                pass

        total_len = get_total_track_length(context, start_frame=scene.frame_start, include_names=active_tracks)
        if log:
            print(f"[TrackForward] ✅ Tracking completed – {frames_tracked} frames tracked, "
                  f"total length {total_len}.")

        # --- Restore original playhead position ---
        try:
            reset_to_frame(context, original_frame)
            scene.frame_current = original_frame
            if log:
                print(f"[TrackForward] 🔁 Playhead restored to original frame {original_frame}.")
        except Exception as ex:
            if log:
                print(f"[TrackForward] ⚠️ Could not restore playhead: {ex!r}")

        return frames_tracked
