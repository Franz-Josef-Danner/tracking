import bpy
import math
import re
from bpy.props import IntProperty, FloatProperty, BoolProperty

# Import utility functions via relative path
from ...helpers.prefix_new import PREFIX_NEW
from ...helpers.prefix_track import PREFIX_TRACK
from ...helpers.prefix_good import PREFIX_GOOD
from ...helpers.prefix_test import PREFIX_TEST
from ...helpers.select_track_tracks import select_track_tracks
from ...helpers.select_new_tracks import select_new_tracks
from ...helpers.select_short_tracks import select_short_tracks
from ...helpers.delete_selected_tracks import delete_selected_tracks
from ...helpers.detection_helpers import (
    detect_features_once,
    find_next_low_marker_frame,
)
from ...helpers.marker_helpers import (
    cleanup_all_tracks,
    ensure_valid_selection,
    select_tracks_by_names,
    select_tracks_by_prefix,
    get_undertracked_markers,
)
from ...helpers.feature_math import (
    calculate_base_values,
    apply_threshold_to_margin_and_distance,
    marker_target_aggressive,
    marker_target_conservative,
)
from ...helpers.tracking_variants import (
    track_bidirectional,
    track_forward_only,
)
from ...helpers.tracking_helpers import track_markers_range
from ...helpers.utils import (
    add_timer,
    jump_to_frame_with_few_markers,
    compute_detection_params,
    pattern_base,
    clamp_pattern_size,
    detect_new_tracks,
    remove_close_tracks,
    add_pending_tracks,
    clean_pending_tracks,
    rename_pending_tracks,
    update_frame_display,
    cycle_motion_model,
)
from ...helpers.set_playhead_to_frame import set_playhead_to_frame
from ..proxy import CLIP_OT_proxy_on, CLIP_OT_proxy_off, CLIP_OT_proxy_build
class CLIP_OT_track_nr1(bpy.types.Operator):
    bl_idname = "clip.track_nr1"
    bl_label = "Track Nr. 1"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    _timer = None
    _state = "INIT"
    _start = 0
    _end = 0
    _tracked = 0
    _next_frame = None
    _cycle_count = 0

    def step_init(self, context):
        """Set defaults and remember the start frame."""
        if bpy.ops.clip.api_defaults.poll():
            bpy.ops.clip.api_defaults()
        self._start = context.scene.frame_current
        return "DETECT"

    MIN_THRESHOLD = 0.0000001  # oder dein gewünschter Mindestwer
    
    def step_detect(self, context):
        """Generate markers using Cycle Detect."""
        clip = getattr(context.space_data, "clip", None)
        if clip is None or not clip.tracking:
            print("\u26a0\ufe0f Kein gültiger Clip – detect wird übersprungen")
            return "TRACK"

        if bpy.ops.clip.proxy_off.poll():
            bpy.ops.clip.proxy_off()


        clip = getattr(context.space_data, "clip", None)

        target = marker_target_aggressive(context.scene.marker_frame)
        target_min = int(target * 0.9)
        target_max = int(target * 1.1)

        attempt = 0
        max_attempts = 10
        threshold = context.scene.threshold_value

        while attempt < max_attempts:
            if bpy.ops.clip.proxy_off.poll():
                bpy.ops.clip.proxy_off()
            detect_features_once(context, clip, threshold)

            marker_count = len(clip.tracking.tracks)
            print(
                f"[Detect Features] count={marker_count}, threshold={threshold:.8f}"
            )

            if target_min <= marker_count <= target_max:
                print("[Detect Features] Zielbereich erreicht")
                break

            threshold *= (marker_count + 0.1) / target
            threshold = max(self.MIN_THRESHOLD, min(threshold, 1.0))

            context.scene.threshold_value = threshold

            cleanup_all_tracks(clip)
            attempt += 1

        context.scene.tracker_threshold = threshold
        print(f"[Track Nr.1] saved threshold {threshold:.8f}")

        if bpy.ops.clip.prefix_new.poll():
            bpy.ops.clip.prefix_new()

        for t in clip.tracking.tracks:
            try:
                if not isinstance(t.name, str) or not t.name.strip():
                    print(f"\u26a0\ufe0f Detected Marker mit ungültigem Namen: {t}")
            except Exception as e:
                print(f"\u26a0\ufe0f Fehler beim Marker-Check: {e}")

        return "TRACK"

    def step_track(self, context):
        """Track markers backward and forward."""
        scene = context.scene
        self._start = scene.frame_current
        enable_proxy()
        if bpy.ops.clip.track_partial.poll():
            track_bidirectional(scene.frame_start, scene.frame_end)
        self._end = scene.frame_current
        self._tracked = self._end - self._start
        print(
            f"[Track Nr.1] start {self._start} end {self._end} tracked {self._tracked}"
        )
        return "DECIDE"

    def step_decide(self, context):
        """Move the playhead to the next frame before cleanup."""
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            print("\u26a0\ufe0f Kein g\u00fcltiger Clip")
            return "MOVE"

        print(
            f"[Track Nr.1] decide end {self._end} tracked {self._tracked} threshold {scene.marker_frame}"
        )

        current = scene.frame_current
        threshold = scene.marker_frame
        frame, count = find_next_low_marker_frame(
            scene,
            clip,
            threshold,
        )
        self._next_frame = frame
        if frame is not None and frame != current:
            jump_to_frame_with_few_markers(
                clip,
                min_marker_count=threshold,
                start_frame=frame,
                end_frame=frame,
            )
            update_frame_display(context)
            print(f"[Track Nr.1] next low frame {frame} ({count} markers)")
            return "CLEANUP"
        else:
            print("[Track Nr.1] finish cycle")
            self.report({'INFO'}, "Zyklus beendet")
            return "RENAME"

    def step_cleanup(self, context):
        """Remove short tracks and keep the playhead at the target frame."""
        if not context.space_data.clip or self._tracked <= 0:
            return "MOVE"

        print("[Track Nr.1] cleanup short tracks")
        cleanup_short_tracks(context)

        return "MOVE"

    def step_move(self, context):
        """Continue to the detection step after housekeeping."""
        self._cycle_count += 1
        if self._cycle_count >= 100:
            self.report({'INFO'}, "Maximale Zyklen erreicht")
            return "RENAME"
        return "DETECT"

    def step_rename(self, context):
        count = rename_new_tracks(context)
        if count:
            self.report({'INFO'}, f"{count} Tracks umbenannt")

        # abschließend kurze TRACK_-Marker entfernen
        cleanup_short_tracks(context)
        return None

    def execute(self, context):
        scene = context.scene
        self._visited_frames = set()
        self._marker_per_frame_start = scene.marker_frame
        # set the starting threshold only once when the operator is triggered
        scene.threshold_value = 0.5
        scene.tracker_threshold = 0.5
        print(
            f"[Track Nr.1] starting threshold {scene.threshold_value:.8f}"
        )
        wm = context.window_manager
        self._timer = add_timer(wm, context.window)
        self._state = "INIT"
        self._cycle_count = 0
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC':
            return self.cancel(context)

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        state_method = getattr(self, f"step_{self._state.lower()}", None)
        if state_method:
            result = state_method(context)
            if result is None:
                return self.cancel(context)
            self._state = result
        else:
            self.report({'ERROR'}, f"Unbekannter Zustand: {self._state}")
            return self.cancel(context)

        return {'RUNNING_MODAL'}


class CLIP_OT_track_nr2(bpy.types.Operator):
    bl_idname = "clip.track_nr2"
    bl_label = "Track Nr. 2"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Movie Clip gefunden.")
            return {'CANCELLED'}

        def handle_frame(frame_number):
            global TRACK_ATTEMPTS
            attempts = TRACK_ATTEMPTS.get(frame_number, 0)
            if attempts > 0:
                if bpy.ops.clip.marker_frame_plus.poll():
                    bpy.ops.clip.marker_frame_plus()
            else:
                if bpy.ops.clip.marker_frame_minus.poll():
                    bpy.ops.clip.marker_frame_minus()
            attempts += 1
            TRACK_ATTEMPTS[frame_number] = attempts
            if attempts > 10:
                self.report(
                    {'ERROR'},
                    f"Zu viele Tracking-Versuche in Frame {frame_number}",
                )
                return False
            return True

        if bpy.ops.clip.setup_defaults.poll():
            bpy.ops.clip.setup_defaults()

        threshold = scene.marker_frame
        frame = jump_to_frame_with_few_markers(
            clip,
            min_marker_count=threshold,
            start_frame=scene.frame_start,
            end_frame=scene.frame_end,
        )
        if frame is not None:
            update_frame_display(context)
            if not handle_frame(frame):
                return {'CANCELLED'}

        cycles = 0
        while True:
            if bpy.ops.clip.test_pattern.poll():
                bpy.ops.clip.test_pattern()
            if bpy.ops.clip.test_motion.poll():
                bpy.ops.clip.test_motion()
            if bpy.ops.clip.test_channel.poll():
                bpy.ops.clip.test_channel()
            if bpy.ops.clip.cycle_detect.poll():
                if bpy.ops.clip.proxy_off.poll():
                    bpy.ops.clip.proxy_off()
                bpy.ops.clip.cycle_detect()
            if bpy.ops.clip.track_partial.poll():
                track_forward_only(scene.frame_start, scene.frame_end)
            if bpy.ops.clip.cleanup.poll():
                bpy.ops.clip.cleanup()
                if bpy.ops.clip.setup_defaults.poll():
                    bpy.ops.clip.setup_defaults()

            cycles += 1
            current = scene.frame_current
            frame = jump_to_frame_with_few_markers(
                clip,
                min_marker_count=threshold,
                start_frame=current + 1,
                end_frame=scene.frame_end,
            )
            if frame is not None and frame != current and cycles < 100:
                update_frame_display(context)
                if not handle_frame(frame):
                    return {'CANCELLED'}
                continue
            if cycles >= 100:
                self.report({'WARNING'}, "Abbruch nach 100 Durchl\u00e4ufen")
            break

        self.report({'INFO'}, f"{cycles} Durchl\u00e4ufe ausgef\u00fchrt")
        return {'FINISHED'}




class CLIP_OT_all_cycle(bpy.types.Operator):
    bl_idname = "clip.all_cycle"
    bl_label = "All Cycle"
    bl_description = (
        "Startet einen kombinierten Tracking-Zyklus ohne Proxy-Bau, der mit Esc abgebrochen werden kann"
    )

    _timer = None
    _state = "DETECT"
    _detect_attempts = 0

    def modal(self, context, event):
        if event.type == 'ESC':
            return self.cancel(context)

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return self.cancel(context)

        if self._state == 'DETECT':
            bpy.ops.clip.all_detect()
            bpy.ops.clip.distance_button()
            delete_selected_tracks()
            clean_pending_tracks(clip)

            count = len(PENDING_RENAME)
            mframe = context.scene.marker_frame
            mf_base = marker_target_aggressive(mframe)
            track_min = mf_base * 0.8
            track_max = mf_base * 1.2

            if track_min <= count <= track_max:
                for t in PENDING_RENAME:
                    t.select = True
                self._detect_attempts = 0
                self._state = 'TRACK'
            else:
                for t in PENDING_RENAME:
                    t.select = True
                delete_selected_tracks()
                clean_pending_tracks(clip)
                self._detect_attempts += 1
                if self._detect_attempts >= 20:
                    self.report({'WARNING'}, "Maximale Wiederholungen erreicht")
                    return self.cancel(context)

        elif self._state == 'TRACK':
            bpy.ops.clip.track_sequence()
            self._state = 'CLEAN'

        elif self._state == 'CLEAN':
            bpy.ops.clip.tracking_length()
            self._state = 'JUMP'

        elif self._state == 'JUMP':
            frame = jump_to_frame_with_few_markers(
                context.space_data.clip,
                min_marker_count=context.scene.marker_frame,
                start_frame=context.scene.frame_start,
                end_frame=context.scene.frame_end,
            )
            if frame is None:
                return self.cancel(context)
            update_frame_display(context)
            self._state = 'DETECT'

        return {'PASS_THROUGH'}

    def execute(self, context):
        self._state = 'DETECT'
        self._detect_attempts = 0
        wm = context.window_manager
        self._timer = add_timer(wm, context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        clip = context.space_data.clip
        if clip:
            rename_pending_tracks(clip)
        return {'CANCELLED'}


class CLIP_OT_step_track(bpy.types.Operator):
    bl_idname = "clip.step_track"
    bl_label = "Step Track"
    bl_description = (
        "Führt Detect, Name Track, Select TRACK und Track Partial aus "
        "und springt anschließend um 'Frames/Track' vor"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        scene = context.scene
        step = scene.frames_track
        end_frame = scene.frame_end

        while scene.frame_current <= end_frame:
            if bpy.ops.clip.all_detect.poll():
                bpy.ops.clip.all_detect()
            if bpy.ops.clip.prefix_track.poll():
                bpy.ops.clip.prefix_track()
            if bpy.ops.clip.select_active_tracks.poll():
                bpy.ops.clip.select_active_tracks()
            if bpy.ops.clip.track_partial.poll():
                bpy.ops.clip.track_partial()

            # Nach dem Tracken erneut Marker erkennen
            if bpy.ops.clip.all_detect.poll():
                bpy.ops.clip.all_detect()

            next_frame = scene.frame_current + step
            if next_frame > end_frame:
                break
            scene.frame_current = next_frame
            update_frame_display(context)

        return {'FINISHED'}



operator_classes = (
    CLIP_OT_track_nr1,
    CLIP_OT_track_nr2,
    CLIP_OT_all_cycle,
    CLIP_OT_step_track,
)

