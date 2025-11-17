# Operator/Master/master_track_operator_backwards.py
import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

# ------------------------------------------------------------
# Helper Imports
# ------------------------------------------------------------
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.scene import get_end_frame, get_start_frame as scene_get_start_frame
from ...Helper.find_clip_editor_area import find_clip_editor_area
from ...Helper.selection_helper import collect_selected_track_names
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.track_markers_helper import track_markers_with_override
from ...Helper.frame_track_progress import compute_marker_progress
from ...Helper.adapt_search_size import adapt_search_size_for_calibrate_tracks
from ...Helper.motion_average_backwards import get_from_selected_tracks_backwards
from ...Helper.formula_helper_backward import apply_formula_on_selected_tracks_backwards

# ------------------------------------------------------------
# Neuer Import: Backward-MarkerCalibration-Helper (ersetzt Forward)
# ------------------------------------------------------------
from ...Helper.marker_position_backward_calibration import (
    correct_marker_positions_backward
)

# ------------------------------------------------------------
# Neuer Import: Zentrales Referenz-Key-System
# ------------------------------------------------------------
from ...Helper.reference_key import (
    get_reference_tracks,
    filter_existing_tracks,
    # NEU: Forward/Backward sollen denselben Referenz-Key verwenden
)

# ------------------------------------------------------------
# NEU: Forward/Backward sollen denselben Referenz-Key verwenden
# ------------------------------------------------------------
from ...Helper.marker_position_forward_calibration import _resolve_reference_key

# ------------------------------------------------------------
# Interner Helper: Speicherung aktiver Tracks in Scene-String
# ------------------------------------------------------------
def store_calibrate_tracks_in_scene(context, track_names: List[str]) -> None:
    """
    Speichert die aktuell selektierten und aktiven Tracks
    im Scene-String 'calibrate_tracks' und 'calibrate_tracks_uuid_map'.
    """
    scene = context.scene
    if not track_names:
        return

    try:
        # Alte Einträge bereinigen
        for key in ("calibrate_tracks", "calibrate_tracks_uuid_map"):
            if key in scene:
                del scene[key]

        clip = getattr(context.space_data, "clip", None)
        if not clip or not getattr(clip, "tracking", None):
            return

        # UUID-Map erzeugen (keine Attribute an Track-Objekten!)
        import uuid as _uuid
        uuid_map: Dict[str, str] = {}
        for name in track_names:
            uuid_map[str(_uuid.uuid4())] = name

        # Speicherung in Szene
        scene["calibrate_tracks"] = ",".join(track_names)
        scene["calibrate_tracks_uuid_map"] = str(uuid_map)

    except Exception as e:
        pass


# ------------------------------------------------------------
# Operator
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_master_track_cycle_backwards(bpy.types.Operator):
    """Frame-by-frame backward tracking with visible progress (non-blocking)."""
    bl_idname = "kaiserlich_tracker.master_track_cycle_backwards"
    bl_label = "Track Cycle Backwards (Modal)"
    bl_description = "Frame-by-frame backward tracking with visible progress (non-blocking)."
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Safety limit (0 = no limit)"
    )

    _timer = None
    _processing_names: List[str]
    _original_selected: List[str]
    _histories: Dict[str, Deque[Tuple[int, float, float]]]
    _window = None
    _area = None
    _region = None
    _space = None
    _start_frame = 0
    _end_frame = 0
    _reset_frame = 0
    _current_frame = 0
    _frames_processed = 0

    # --------------------------------------------------------
    # Initialization
    # --------------------------------------------------------

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "No active clip.")
            return {"CANCELLED"}

        # Determine scene start and end
        self._start_frame = scene_get_start_frame(context)
        self._end_frame = get_end_frame(context)
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        # Capture selection
        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            self.report({'WARNING'}, "No tracks selected.")
            return {"CANCELLED"}

        self._processing_names = list(self._original_selected)

        # Find CLIP_EDITOR area
        self._window, self._area, self._region, self._space = find_clip_editor_area(clip)
        if not self._window:
            self.report({'ERROR'}, "No CLIP_EDITOR area found.")
            return {"CANCELLED"}

        # Determine playhead start position
        self._reset_frame = int(scene.frame_current)
        scene_current = int(self._reset_frame)
        if scene_current < self._start_frame:
            self._current_frame = self._start_frame
        elif scene_current > self._end_frame:
            self._current_frame = self._end_frame
        else:
            self._current_frame = scene_current

        # Set playhead
        self._space.clip_user.frame_current = int(self._current_frame)
        scene.frame_current = int(self._current_frame)

        # Initialize histories
        self._histories = {name: deque(maxlen=10) for name in self._processing_names}

        # Fix selection
        tracking = clip.tracking
        for tr in tracking.tracks:
            tr.select = (tr.name in self._original_selected)
        # --------------------------------------------------------
        # NEU: Referenz-Key bestimmen (identisch zu Forward)
        # --------------------------------------------------------
        try:
            scene = context.scene
            self._active_ref_key = _resolve_reference_key(scene)
        except Exception:
            # Falls kein Key bestimmt werden kann → None,
            # Backward arbeitet dann wie bisher ohne Referenz-Key.
            self._active_ref_key = None

        # (Forward speichert den aktiven Key nicht als Scene-Prop,
        # daher hier ebenfalls kein Scene-Write.)

        # Activate timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Modal Loop
    # --------------------------------------------------------

    def modal(self, context, event):
        if event.type == 'ESC':
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        if event.type != 'TIMER':
            return {"PASS_THROUGH"}

        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        tracking = clip.tracking

        # Update histories
        for name in list(self._processing_names):
            tr = tracking.tracks.get(name)
            if not tr:
                continue
            mk = tr.markers.find_frame(int(self._current_frame))
            if mk:
                self._histories[name].append((self._current_frame, mk.co[0], mk.co[1]))

        # --- Vor jedem Calibration-Step sichern ---
        store_calibrate_tracks_in_scene(context, self._processing_names)

        # Apply optional optimization formula
        get_from_selected_tracks_backwards(context, max_frames=5)
        apply_formula_on_selected_tracks_backwards(context, max_frames=5)


        # -------------------------------------------------------
        # BACKWARD CALIBRATION STEP (mit Referenzwahl good/best)
        # -------------------------------------------------------
        try:
            scene = context.scene

            # calibrate_tracks aus Scene lesen
            calibrate_raw = scene.get("calibrate_tracks", "")
            if isinstance(calibrate_raw, str):
                calibrate_tracks = [
                    t.strip() for t in calibrate_raw.split(",") if t.strip()
                ]
            else:
                calibrate_tracks = []

            if not calibrate_tracks:
                pass
            else:
                # -------------------------------------------------------
                # Referenz über zentrales Referenz-Key-System
                # -------------------------------------------------------
                ref_names = get_reference_tracks(scene)
                ref_names = filter_existing_tracks(context, ref_names)

                # --- Dead-Reference Cleanup (neu, Punkt 4) ---
                clip = getattr(context.space_data, "clip", None)
                if not clip:
                    return {"CANCELLED"}

                tracking = clip.tracking

                calibrate_tracks = [t for t in calibrate_tracks if t in tracking.tracks]
                ref_names = [t for t in ref_names if t in tracking.tracks]

                # Wenn nach Cleanup keine gültigen Tracks mehr existieren → skip
                if not ref_names or not calibrate_tracks:
                    pass
                else:
                    # Frame-Kontexte für rückwärts Tracking
                    f_now = int(self._current_frame)

                    f_next  = int(f_now) + 1
                    f_next2 = int(f_now) + 2
                    f_next3 = int(f_now) + 3

                    # Clip-Limits
                    if f_next > self._end_frame:  f_next = None
                    if f_next2 > self._end_frame: f_next2 = None
                    if f_next3 > self._end_frame: f_next3 = None

                    if f_next is not None:
                        correct_marker_positions_backward(
                            scene,
                            ref_names,
                            calibrate_tracks,
                            f_now,
                            f_next, f_next2, f_next3
                        )


        except Exception:
            pass

        # adapt search size
        try:
            adapt_search_size_for_calibrate_tracks(context)
        except Exception:
            pass
        
        # Perform backward tracking step
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=True, sequence=False
        )

        if not success:
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Filter active tracks
        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )

        # Exit conditions
        if not self._processing_names:
            self._finish(context)
            return {"FINISHED"}

        if self.max_frames > 0 and self._frames_processed >= self.max_frames:
            self._finish(context)
            return {"FINISHED"}

        # Step backward
        scene = context.scene
        if int(self._space.clip_user.frame_current) == int(self._current_frame):
            self._space.clip_user.frame_current = int(self._current_frame) - 1

        if int(self._space.clip_user.frame_current) < int(self._start_frame):
            self._space.clip_user.frame_current = int(self._start_frame)

        scene.frame_current = int(self._space.clip_user.frame_current)
        self._current_frame = int(scene.frame_current)
        self._frames_processed += 1

        if int(self._current_frame) <= int(self._start_frame):
            self._finish(context)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Finalization / Cleanup
    # --------------------------------------------------------

    def _finish(self, context, cancelled: bool = False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None

        # Restore selection
        clip = getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            for tr in clip.tracking.tracks:
                tr.select = (tr.name in self._original_selected)

        # Reset playhead
        try:
            reset_to_frame(context, self._reset_frame)
        except Exception:
            pass

        # Compute quality metrics
        try:
            from ...Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            quality_percent = float(metrics.get("prozent", 100.0))
            context.scene.kaiserlich_quality_percent = f"{int(round(quality_percent))}%"

            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "CLIP_EDITOR":
                        for region in area.regions:
                            if region.type == "UI":
                                region.tag_redraw()
        except Exception:
            quality_percent = 100.0

        # Compute marker progress
        try:
            _, perc = compute_marker_progress(context.scene, update_ui=True)
            context.scene.kaiserlich_marker_progress = f"{int(round(perc))}%"
        except Exception:
            pass


        # Hand over control to forward tracking operator
        if not cancelled:
            try:
                clip = getattr(context.space_data, "clip", None)
                if clip is None:
                    return

                window, area, region, space = find_clip_editor_area(clip)
                if not window:
                    return

                with context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.kaiserlich_tracker.master_track_cycle()
            except Exception:
                pass


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_track_cycle_backwards)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_track_cycle_backwards)
