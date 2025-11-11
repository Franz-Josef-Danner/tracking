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
    find_active_tracks_key,
    _resolve_reference_key,
)

# ------------------------------------------------------------
# Interner Helper: Speicherung aktiver Tracks in Scene-String
# ------------------------------------------------------------
def store_calibrate_tracks_in_scene(context, track_names: List[str]) -> None:
    """
    Speichert die aktuell selektierten und aktiven Tracks
    im Scene-String 'calibrate_tracks' und 'calibrate_tracks_uuid_map'.
    UUIDs werden ausschließlich in einer temporären Map verwaltet,
    nicht als Attribut an den MovieTrackingTrack-Objekten.
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

        import uuid as _uuid
        uuid_map: Dict[str, str] = {}

        # UUIDs neu erzeugen – keine Attribute am Track selbst
        for name in track_names:
            uuid_map[str(_uuid.uuid4())] = name

        # Speicherung als Scene-Strings
        scene["calibrate_tracks"] = ",".join(track_names)
        scene["calibrate_tracks_uuid_map"] = str(uuid_map)

    except Exception as e:
        print(f"[store_calibrate_tracks_in_scene] Fehler: {e}")

# =====================================================================
# Hauptoperator
# =====================================================================
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

        # Start- und End-Frame
        self._start_frame = ph_get_start_frame(context)
        self._end_frame = get_end_frame(context)
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        # Aktuelle Track-Selektion
        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            self.report({'WARNING'}, "No tracks selected.")
            return {"CANCELLED"}

        self._processing_names = list(self._original_selected)

        # Clip-Editor finden
        self._window, self._area, self._region, self._space = find_clip_editor_area(clip)
        if not self._window:
            self.report({'ERROR'}, "No CLIP_EDITOR area found.")
            return {"CANCELLED"}

        # Startframe setzen
        self._current_frame = max(self._start_frame, int(scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        scene.frame_current = self._current_frame

        # Historien vorbereiten
        self._histories = {name: deque(maxlen=10) for name in self._processing_names}

        # Auswahl fixieren
        tracking = clip.tracking
        for tr in tracking.tracks:
            tr.select = (tr.name in self._original_selected)

        # --------------------------------------------------------
        # Referenz-Key bestimmen
        # --------------------------------------------------------
        self._active_ref_key = _resolve_reference_key(scene)

        # --------------------------------------------------------
        # NEU: Aktuell selektierte und aktive Tracks speichern
        # --------------------------------------------------------
        store_calibrate_tracks_in_scene(context, self._processing_names)

        # --------------------------------------------------------
        # Timer starten
        # --------------------------------------------------------
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

        # Historien aktualisieren
        for name in list(self._processing_names):
            tr = tracking.tracks.get(name)
            if not tr:
                continue
            mk = tr.markers.find_frame(self._current_frame)
            if mk and not mk.mute:
                self._histories[name].append((self._current_frame, mk.co[0], mk.co[1]))

        # -----------------------------------------------
        # 1) Vor jedem Calibration-Step sichern
        # -----------------------------------------------
        store_calibrate_tracks_in_scene(context, self._processing_names)

        # Danach würde marker_position_forward_calibration.py aufgerufen werden
        # (hier nur vorbereitend, damit calibrate_tracks aktuell ist)

        # -----------------------------------------------
        # 2) Adaptive Formel
        # -----------------------------------------------
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception:
            pass

        # -----------------------------------------------
        # 3) Tracking-Step
        # -----------------------------------------------
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )
        if not success:
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Frame fortsetzen
        scene = context.scene
        if self._space.clip_user.frame_current == self._current_frame:
            self._space.clip_user.frame_current += 1
        if self._space.clip_user.frame_current > self._end_frame:
            self._space.clip_user.frame_current = self._end_frame

        scene.frame_current = self._space.clip_user.frame_current
        self._current_frame = self._space.clip_user.frame_current
        self._frames_processed += 1

        # Aktive Tracks filtern
        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )

        # Abbruchbedingungen
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
    # Abschluss / Cleanup
    # --------------------------------------------------------

    def _finish(self, context, cancelled: bool = False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None

        # Ursprüngliche Auswahl wiederherstellen
        clip = getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            for tr in clip.tracking.tracks:
                tr.select = (tr.name in self._original_selected)

        # Zurücksetzen
        try:
            reset_to_frame(context, self._start_frame)
        except Exception:
            pass

        # Progress aktualisieren
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

        # Folge-Operator starten
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
