import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

# Helper-Importe
from ..Helper.clip_editor_finder import find_clip_editor_area
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.track_activity_filter import filter_active_tracks_at_frame
from ..Helper.track_cycle_init import initialize_tracking_state, restore_selection
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
from ..Helper.scene import get_start_frame as sc_get_start_frame, get_end_frame


class KAISERLICHTRACKER_OT_track_cycle_backwards(bpy.types.Operator):
    """Frame-by-Frame Rückwärts-Tracking mit sichtbarem Fortschritt (nicht blockierend)."""
    bl_idname = "kaiserlich_tracker.track_cycle_backwards"
    bl_label = "Track Zyklus (Modal Rückwärts)"
    bl_description = (
        "Trackt selektierte Marker frameweise rückwärts mit Timer – UI bleibt responsiv, "
        "Playhead und Markerupdates sichtbar."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Sicherheitslimit (0 = kein Limit)"
    )

    _timer = None
    _processing_names: List[str]
    _original_selected: List[str]
    _histories: Dict[str, Deque[Tuple[int, float, float]]]
    _window = None
    _area = None
    _region = None
    _space = None
    _frame_start = 0
    _frame_end = 0
    _current_frame = 0
    _frames_processed = 0
    _start_frame_saved = 0

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip.")
            return {"CANCELLED"}

        self._start_frame_saved = ph_get_start_frame(context)
        self._frame_start = sc_get_start_frame(context)
        self._frame_end = get_end_frame(context)
        if self._frame_end < self._frame_start:
            self._frame_end = self._frame_start

        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            self.report({'WARNING'}, "Keine Tracks selektiert.")
            return {"CANCELLED"}

        self._processing_names = list(self._original_selected)
        self._window, self._area, self._region, self._space = find_clip_editor_area(clip)
        if not self._window:
            self.report({'ERROR'}, "Keine CLIP_EDITOR Area gefunden.")
            return {"CANCELLED"}

        self._current_frame = int(scene.frame_current)
        self._current_frame = max(min(self._current_frame, self._frame_end), self._frame_start)
        self._space.clip_user.frame_current = scene.frame_current = self._current_frame

        self._histories = initialize_tracking_state(clip, self._processing_names)
        restore_selection(clip, self._original_selected)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        print("[Kaiserlich Tracker][Modal Rückwärts] Startet Tracking-Zyklus...")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == 'ESC':
            print("[Kaiserlich Tracker][Modal Rückwärts] Abgebrochen durch Benutzer.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        if event.type != 'TIMER':
            return {"PASS_THROUGH"}

        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        tracking = clip.tracking
        for name in list(self._processing_names):
            tr = tracking.tracks.get(name)
            if tr:
                mk = tr.markers.find_frame(self._current_frame)
                if mk:
                    self._histories[name].append((self._current_frame, mk.co[0], mk.co[1]))

        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception:
            pass

        with bpy.context.temp_override(window=self._window, area=self._area, region=self._region, space_data=self._space):
            try:
                bpy.ops.clip.track_markers(backwards=True, sequence=False)
            except Exception:
                print("[Kaiserlich Tracker][Modal Rückwärts] Tracking-Fehler.")
                self._finish(context, cancelled=True)
                return {"CANCELLED"}

        scene = context.scene
        if self._space.clip_user.frame_current == self._current_frame:
            self._space.clip_user.frame_current -= 1
        if self._space.clip_user.frame_current < self._frame_start:
            self._space.clip_user.frame_current = self._frame_start

        scene.frame_current = self._space.clip_user.frame_current
        self._current_frame = self._space.clip_user.frame_current
        self._frames_processed += 1

        self._processing_names, _ = filter_active_tracks_at_frame(context, self._processing_names, self._current_frame)

        if self._current_frame <= self._frame_start:
            print("[Kaiserlich Tracker][Modal Rückwärts] Szenenstart erreicht.")
            self._finish(context)
            return {"FINISHED"}

        if not self._processing_names:
            print("[Kaiserlich Tracker][Modal Rückwärts] Keine aktiven Tracks mehr.")
            self._finish(context)
            return {"FINISHED"}

        if self.max_frames > 0 and self._frames_processed >= self.max_frames:
            print("[Kaiserlich Tracker][Modal Rückwärts] Sicherheitslimit erreicht.")
            self._finish(context)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}

    def _finish(self, context, cancelled: bool = False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None

        clip = getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            restore_selection(clip, self._original_selected)

        try:
            reset_to_frame(context, self._start_frame_saved)
        except Exception:
            pass

        print(
            "[Kaiserlich Tracker][Modal Rückwärts] Zyklus beendet."
            if not cancelled else
            "[Kaiserlich Tracker][Modal Rückwärts] Abgebrochen."
        )


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle_backwards)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle_backwards)