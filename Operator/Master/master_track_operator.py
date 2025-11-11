# Operator/Master/master_track_operator.py
import bpy
from typing import List, Tuple, Dict, Deque, Optional
from collections import deque

# ------------------------------------------------------------
# Helper Imports (bestehend)
# ------------------------------------------------------------
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
from ...Helper.scene import get_end_frame
from ...Helper.find_clip_editor_area import find_clip_editor_area
from ...Helper.selection_helper import collect_selected_track_names
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.track_markers_helper import track_markers_with_override
from ...Helper.frame_track_progress import compute_marker_progress

# ------------------------------------------------------------
# Neuer Korrektur-Helper
# ------------------------------------------------------------
from ...Helper.marker_position_forward_calibration import (
    correct_marker_positions,
    marker_exists,  # optional nützlich für Guards
)

class KAISERLICHTRACKER_OT_master_track_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.master_track_cycle"
    bl_label = "Track Cycle (Modal)"
    bl_description = "Performs a non-blocking forward tracking cycle for all selected markers"
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
    _current_frame = 0
    _frames_processed = 0

    # --------------------------------------------------------
    # Initialization
    # --------------------------------------------------------

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "No active clip found.")
            return {"CANCELLED"}

        # Get start and end frames
        self._start_frame = ph_get_start_frame(context)
        self._end_frame = get_end_frame(context)
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        # Collect current track selection
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

        # Set starting frame
        self._current_frame = max(self._start_frame, int(scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        scene.frame_current = self._current_frame

        # Initialize histories for each track
        self._histories = {name: deque(maxlen=10) for name in self._processing_names}

        # Lock current selection
        tracking = clip.tracking
        for tr in tracking.tracks:
            tr.select = (tr.name in self._original_selected)

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
            mk = tr.markers.find_frame(self._current_frame)
            if mk and not mk.mute:
                self._histories[name].append((self._current_frame, mk.co[0], mk.co[1]))

        # ---------------------------
        # 1) Positions-Stabilisierung
        # ---------------------------
        # Frames: a = current, b = previous, c = prev-1, d = prev-2 (falls vorhanden)
        a = int(self._current_frame)
        b = max(self._start_frame, a - 1)
        c = b - 1 if (b - 1) >= self._start_frame else None
        d = (c - 1) if (c is not None and c - 1 >= self._start_frame) else None

        # Selektierte Tracks als Objekte
        selected_tracks = [tracking.tracks.get(nm) for nm in self._processing_names]
        selected_tracks = [t for t in selected_tracks if t is not None]

        try:
            # Nur ausführen, wenn mindestens 1 Frame zurückliegt
            if a > self._start_frame and selected_tracks:
                # Marker-Korrektur-Helfer (mit Szenen-Scan für good/best_tracks)
                correct_marker_positions(
                    context.scene,     # -> Szene (liefert Strings & Marker-Mengen)
                    selected_tracks,   # -> zu korrigierende Markerobjekte
                    a, b, c, d         # -> aktuelle + bis zu 3 vorherige Frames
                )
        except Exception as e:
            print(f"[MasterTrackCycle][WARN] Marker-Korrektur übersprungen: {e}")


        # ---------------------------
        # 2) Adaptive Formel (deine Logik)
        # ---------------------------
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception:
            pass

        # ---------------------------
        # 3) Tracking-Step
        # ---------------------------
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )
        if not success:
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Advance frame
        scene = context.scene
        if self._space.clip_user.frame_current == self._current_frame:
            self._space.clip_user.frame_current += 1
        if self._space.clip_user.frame_current > self._end_frame:
            self._space.clip_user.frame_current = self._end_frame

        scene.frame_current = self._space.clip_user.frame_current
        self._current_frame = self._space.clip_user.frame_current
        self._frames_processed += 1

        # Filter active tracks
        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )

        # Termination conditions
        if self._current_frame >= self._end_frame:
            self._finish(context)
            return {"FINISHED"}

        if not self._processing_names:
            self._finish(context)
            return {"FINISHED"}

        if self.max_frames > 0 and self._frames_processed >= self.max_frames:
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

        # Restore original selection
        clip = getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            for tr in clip.tracking.tracks:
                tr.select = (tr.name in self._original_selected)

        # Optional: Reset zum Startframe, damit der Folge-Operator konsistent beginnt
        try:
            reset_to_frame(context, self._start_frame)
        except Exception:
            pass

        # Progress/QoS aktualisieren (defensiv gekapselt)
        try:
            metrics = None
            try:
                from ...Helper.track_quality_metrics import compute_track_quality_metrics
                metrics = compute_track_quality_metrics(context)
                quality_percent = float(metrics.get("prozent", 100.0))
                context.scene.kaiserlich_quality_percent = f"{int(round(quality_percent))}%"
            except Exception:
                pass

            try:
                _, perc = compute_marker_progress(context.scene, update_ui=True)
                context.scene.kaiserlich_marker_progress = f"{int(round(perc))}%"
            except Exception:
                pass
        except Exception:
            pass

        # Chain to next operator (nur wenn nicht abgebrochen)
        if not cancelled:
            try:
                bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            except Exception:
                pass

# ------------------------------------------------------------
# Register
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_track_cycle)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_track_cycle)
